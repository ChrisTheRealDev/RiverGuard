package com.riverguard.v2;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Build;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import static com.riverguard.v2.PhoneValidation.*;

/** One application-scoped database/receiver. The Service, never an Activity, owns monitoring. */
final class PhoneRuntime {
    private static PhoneRuntime instance;
    static synchronized PhoneRuntime get(Context context){if(instance==null)instance=new PhoneRuntime(context.getApplicationContext());return instance;}
    final PhoneStore store;
    private final Context context;
    private final PhoneReceiver receiver;
    private ScheduledExecutorService monitor;
    private volatile boolean enabled;
    private volatile String error;
    private volatile MonitoringService service;
    private PhoneRuntime(Context context){this.context=context;store=new PhoneStore(context);receiver=new PhoneReceiver(store,8000);store.receiverEnabled(false);MonitoringService.createChannels(context);}
    private boolean notificationPermissionAllowed(){return (Build.VERSION.SDK_INT<33||ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED)&&NotificationManagerCompat.from(context).areNotificationsEnabled();}
    private boolean channelAllowed(String id){if(Build.VERSION.SDK_INT<26)return true;NotificationChannel channel=context.getSystemService(NotificationManager.class).getNotificationChannel(id);return channel!=null&&channel.getImportance()!=NotificationManager.IMPORTANCE_NONE;}
    boolean notificationsAllowed(){return notificationPermissionAllowed()&&channelAllowed(MonitoringService.ALERTS)&&channelAllowed(MonitoringService.REVIEWS);}
    boolean canNotify(int level){return notificationPermissionAllowed()&&channelAllowed(level>=3?MonitoringService.ALERTS:MonitoringService.REVIEWS);}
    boolean wifiConnected(){ConnectivityManager cm=(ConnectivityManager)context.getSystemService(Context.CONNECTIVITY_SERVICE);if(cm==null)return false;for(Network n:cm.getAllNetworks()){NetworkCapabilities caps=cm.getNetworkCapabilities(n);if(caps!=null&&caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI))return true;}return false;}
    synchronized JSONObject info(){JSONObject info=receiver.info(enabled);put(info,"notificationsAllowed",notificationsAllowed());put(info,"wifiConnected",wifiConnected());String problem=error;if(enabled&&!wifiConnected())problem="Wi-Fi is disconnected. Monitoring cannot receive the station until both devices share Wi-Fi.";if(problem!=null)put(info,"error",problem);return info;}
    synchronized void requested(boolean requested){enabled=requested;store.receiverEnabled(requested);}
    synchronized boolean isRequested(){return enabled;}
    synchronized void failed(String message){error=message;enabled=false;store.receiverEnabled(false);}
    synchronized void start(MonitoringService owner) {
        service=owner;
        if(monitor!=null)return;
        enabled=true;store.receiverEnabled(true);error=null;
        monitor=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"riverguard-v2-monitor");t.setDaemon(true);return t;});
        monitor.scheduleWithFixedDelay(()->tick(owner),0,3,TimeUnit.SECONDS);
    }
    private void tick(MonitoringService owner){
        try {
            synchronized(this){if(!enabled||service!=owner)return;if(!receiver.isRunning())receiver.start();error=null;}
            owner.renewLocks();
            JSONArray stations=store.stations();
            for(int i=0;i<stations.length();i++){
                String device=stations.getJSONObject(i).getString("deviceId");JSONArray events=store.evaluateAlerts(device,System.currentTimeMillis());
                JSONObject highest=null;
                for(int j=0;j<events.length();j++){JSONObject event=events.getJSONObject(j);if(event.optString("phase").equals("active")&&canNotify(event.optInt("level"))&&(highest==null||event.optInt("level")>highest.optInt("level")))highest=event;}
                synchronized(this){if(!enabled||service!=owner)return;if(highest!=null)owner.notifyAlert(device,highest);}
            }
        }catch(Exception failure){synchronized(this){if(!enabled||service!=owner)return;error="Monitoring could not read or store sensor data. Check port 8000, reopen RiverGuard and retry; do not clear app data.";owner.showRuntimeError();}}
    }
    synchronized void stop(MonitoringService owner){if(owner!=null&&service!=null&&service!=owner)return;enabled=false;store.receiverEnabled(false);receiver.stop();ScheduledExecutorService old=monitor;monitor=null;service=null;if(old!=null)old.shutdownNow();}
}
