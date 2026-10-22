package com.riverguard.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import androidx.activity.result.ActivityResult;
import androidx.lifecycle.Lifecycle;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import static com.riverguard.app.PhoneValidation.*;

/** Private local-page bridge. There are no HTTP endpoints for privileged UI operations. */
@CapacitorPlugin(name="RiverGuardPhone")
public class RiverGuardPhonePlugin extends Plugin {
    private PhoneStore store;
    private PhoneReceiver receiver;
    private final Object receiverLock=new Object();
    private volatile boolean resumed, destroyed;
    private String receiverError;
    private PendingDocument pending;
    private volatile boolean documentBusy;
    private final ThreadPoolExecutor worker=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(64),new ThreadPoolExecutor.AbortPolicy());
    private final ThreadPoolExecutor documentWorker=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(1),new ThreadPoolExecutor.AbortPolicy());
    private interface Operation { JSONObject run() throws Exception; }
    @Override public void load() {
        store=new PhoneStore(getContext());
        receiver=new PhoneReceiver(store,8000);
        getActivity().runOnUiThread(()->{
            resumed=getActivity().getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.RESUMED);
            try {worker.execute(()->{try{updateReceiver();}catch(Exception error){receiverError="Sensor receiver could not start. Check port 8000 and try again.";}});}catch(java.util.concurrent.RejectedExecutionException ignored){}
        });
    }
    private boolean trusted() {
        if(destroyed||getBridge()==null||getBridge().getWebView()==null) return false;
        String current=getBridge().getWebView().getUrl();
        if(current==null)return false;
        Uri actual=Uri.parse(current),local=Uri.parse(getBridge().getLocalUrl());
        return local.getScheme().equals(actual.getScheme())&&local.getHost().equals(actual.getHost())&&local.getPort()==actual.getPort();
    }
    private void execute(PluginCall call,Operation operation) {
        executeOn(call,operation,worker);
    }
    private void executeOn(PluginCall call,Operation operation,ThreadPoolExecutor executor) {
        getActivity().runOnUiThread(()->{
            if(!trusted()){call.reject("Only the bundled phone interface can access phone data.","403");return;}
            try {executor.execute(()->{
                try {if(destroyed)throw new Problem(503,"The phone app is closing.");call.resolve(new JSObject(operation.run().toString()));}
                catch(Problem error){call.reject(error.getMessage(),String.valueOf(error.status));}
                catch(Exception error){call.reject("Phone storage or receiver is unavailable. Retry without clearing app data.","500");}
            });}catch(java.util.concurrent.RejectedExecutionException error){if(executor==documentWorker)documentBusy=false;call.reject("Phone is busy. Please try again.","503");}
        });
    }
    private JSONObject info() {
        synchronized(receiverLock){JSONObject value=receiver.info(store.receiverEnabled());if(receiverError!=null)put(value,"error",receiverError);return value;}
    }
    private void updateReceiver() throws Exception {
        synchronized(receiverLock){
            if(!destroyed&&resumed&&store.receiverEnabled()){
                if(!receiver.isRunning())receiver.start();
                receiverError=null;
            }else receiver.stop();
        }
    }
    @PluginMethod public void getState(PluginCall call){execute(call,()->store.getState(string(call.getData(),"key",1,160)));}
    @PluginMethod public void setState(PluginCall call){execute(call,()->store.setState(string(call.getData(),"key",1,160),call.getData().opt("value")));}
    @PluginMethod public void registerStation(PluginCall call){execute(call,()->store.register(station(call.getString("deviceId")),call.getBoolean("rotate",false)));}
    @PluginMethod public void getSettings(PluginCall call){execute(call,()->store.settings(station(call.getString("deviceId"))));}
    @PluginMethod public void saveSettings(PluginCall call){execute(call,()->store.saveSettings(station(call.getString("deviceId")),integer(call.getData(),"expectedRevision",0,Integer.MAX_VALUE-1),requireObject(call.getData(),"settings")));}
    @PluginMethod public void listStations(PluginCall call){execute(call,()->json("items",store.stations(),"receiver",info()));}
    @PluginMethod public void listReadings(PluginCall call){execute(call,()->store.readings(call.getString("source"),station(call.getString("deviceId")),call.getInt("limit",120),call.getString("cursor")));}
    @PluginMethod public void appendDemo(PluginCall call){execute(call,()->store.appendDemo(requireObject(call.getData(),"payload")));}
    @PluginMethod public void setReceiver(PluginCall call){execute(call,()->{
        boolean enabled=bool(call.getData(),"enabled");store.receiverEnabled(enabled);
        try{updateReceiver();}catch(Exception error){store.receiverEnabled(false);receiverError="Could not listen on port 8000. Another app may be using it.";throw new Problem(503,receiverError);}
        return info();
    });}
    private static class PendingDocument {
        String type,source,device,name,mime,content;
        PendingDocument(String type){this.type=type;}
    }
    private void choose(PluginCall call,PendingDocument next){
        getActivity().runOnUiThread(()->{
            if(!trusted()){call.reject("Only the bundled phone interface can export data.","403");return;}
            if(pending!=null||documentBusy){call.reject("Finish the current document save first.","409");return;}
            documentBusy=true;
            pending=next;
            Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(next.mime).putExtra(Intent.EXTRA_TITLE,next.name);
            try{startActivityForResult(call,intent,"documentSelected");}catch(Exception error){pending=null;documentBusy=false;call.reject("No document picker is available on this phone.","503");}
        });
    }
    @PluginMethod public void exportData(PluginCall call){
        try{PendingDocument next=new PendingDocument("readings");next.source=call.getString("source");if(!"simulation".equals(next.source)&&!"esp32".equals(next.source))throw new Problem(422,"Choose demo or sensor readings.");next.device=station(call.getString("deviceId"));next.mime="text/csv";next.name="RiverGuard-"+next.device+"-readings.csv";choose(call,next);}catch(Problem error){call.reject(error.getMessage(),String.valueOf(error.status));}
    }
    @PluginMethod public void saveText(PluginCall call){
        try{PendingDocument next=new PendingDocument("text");next.name=string(call.getData(),"name",1,100);if(!next.name.matches("[A-Za-z0-9_.-]+")||next.name.startsWith("."))throw new Problem(422,"Use a simple document filename.");next.mime=string(call.getData(),"mime",1,80);if(!next.mime.equals("text/plain")&&!next.mime.equals("application/json"))throw new Problem(422,"Unsupported document type.");next.content=string(call.getData(),"content",0,65536);if(next.content.getBytes(StandardCharsets.UTF_8).length>65536)throw new Problem(413,"Document is too large.");choose(call,next);}catch(Problem error){call.reject(error.getMessage(),String.valueOf(error.status));}
    }
    @PluginMethod public void saveGuide(PluginCall call){PendingDocument next=new PendingDocument("guide");next.name="RiverGuard-Friend-Setup.pdf";next.mime="application/pdf";choose(call,next);}
    @ActivityCallback private void documentSelected(PluginCall call,ActivityResult result){
        PendingDocument selected=pending;pending=null;
        if(call==null){documentBusy=false;return;}
        if(selected==null||result.getResultCode()!=Activity.RESULT_OK||result.getData()==null||result.getData().getData()==null){documentBusy=false;call.resolve(toJS(json("saved",false)));return;}
        Uri destination=result.getData().getData();
        executeOn(call,()->{
          try {
            try(OutputStream output=getContext().getContentResolver().openOutputStream(destination)){
                if(output==null)throw new Problem(500,"Cannot open the selected document.");
                if(selected.type.equals("guide")){try(InputStream input=getContext().getAssets().open("public/guides/RiverGuard-Friend-Setup.pdf")){byte[] buffer=new byte[16384];int read;while((read=input.read(buffer))!=-1)output.write(buffer,0,read);}}
                else if(selected.type.equals("text")){output.write(selected.content.getBytes(StandardCharsets.UTF_8));}
                else{OutputStreamWriter writer=new OutputStreamWriter(output,StandardCharsets.UTF_8);store.export(selected.source,selected.device,writer);writer.flush();}
            }
            return json("saved",true);
          } finally {documentBusy=false;}
        },documentWorker);
    }
    private JSObject toJS(JSONObject object){try{return new JSObject(object.toString());}catch(org.json.JSONException error){throw new IllegalStateException(error);}}
    @Override protected void handleOnPause(){resumed=false;synchronized(receiverLock){receiver.stop();}}
    @Override protected void handleOnResume(){resumed=true;try{worker.execute(()->{try{updateReceiver();}catch(Exception error){receiverError="Sensor receiver could not restart. Check the connection and try again.";}});}catch(java.util.concurrent.RejectedExecutionException ignored){}}
    @Override protected void handleOnDestroy(){
        destroyed=true;resumed=false;synchronized(receiverLock){receiver.stop();}
        worker.shutdown();
        documentWorker.shutdown();
        new Thread(()->{try{worker.awaitTermination(30,TimeUnit.SECONDS);documentWorker.awaitTermination(120,TimeUnit.SECONDS);}catch(InterruptedException error){Thread.currentThread().interrupt();}if(worker.isTerminated()&&documentWorker.isTerminated())store.close();},"riverguard-close").start();
    }
    @Override protected Bundle saveInstanceState(){return null;}
}
