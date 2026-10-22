import {useEffect,useRef,useState} from 'react';
import {platform,persist,errorText,type Source,type RecordRow,type Station,type Receiver,type Monitoring} from './platform';
import './domain.js';
export const domain=globalThis.RiverGuardDomain;
export type Watch={elevated:number;warning:number;rise_limit:number};
export const defaultWatch:Watch={elevated:70,warning:100,rise_limit:10};
export const scenarios=['Normal river','Cloudier water','Sudden change','Rising water level'];
type Preferences={source:Source;deviceId:string;scenario:string;running:boolean};
const initial:Preferences={source:'simulation',deviceId:'demo-station',scenario:scenarios[0],running:true};
export function useMonitor(){
 const [ready,setReady]=useState(false),[preferences,setPreferences]=useState(initial),[rows,setRows]=useState<RecordRow[]>([]),[stations,setStations]=useState<Station[]>([]),[receiver,setReceiver]=useState<Receiver>({running:false,enabled:false,port:8000,addresses:[]}),[monitoring,setMonitoring]=useState<Monitoring>({running:false,enabled:false,notificationsAllowed:false}),[watch,setWatch]=useState(defaultWatch),[error,setError]=useState(''),[total,setTotal]=useState(0),[clock,setClock]=useState(Date.now());
 const current=useRef(preferences),busy=useRef(false),demoBusy=useRef(false),step=useRef(0),selection=useRef(0);current.current=preferences;
 const refresh=async()=>{if(busy.current)return;busy.current=true;const p=current.current,serial=selection.current;try{const [list,result,status]=await Promise.all([platform.listStations(),platform.listReadings({source:p.source,deviceId:p.deviceId,limit:120}),platform.getMonitoring()]);if(serial!==selection.current)return;setStations(list.items);setReceiver(list.receiver);setMonitoring(status);setRows(result.items);setTotal(result.total);setError('');}catch(e){setError(errorText(e));}finally{busy.current=false;}};
 useEffect(()=>{let active=true;(async()=>{try{const saved=(await platform.getState({key:'v2-preferences'})).value;const p={...initial,...saved};if(p.source!=='esp32'&&p.source!=='simulation')p.source='simulation';current.current=p;step.current=Number((await platform.getState({key:'v2-demo-step'})).value)||0;const demo=await platform.listReadings({source:'simulation',deviceId:'demo-station',limit:1});if(!demo.total){for(let i=0;i<16;i++)await platform.appendDemo({payload:domain.syntheticSample(scenarios[0],i,Date.now()-(15-i)*2000)});step.current=16;}if(active){setPreferences(p);setReady(true);}}catch(e){if(active)setError(errorText(e));}})();return()=>{active=false;};},[]);
 useEffect(()=>{if(!ready)return;persist('v2-preferences',preferences).catch(e=>setError(errorText(e)));},[ready,preferences]);
 useEffect(()=>{if(!ready)return;selection.current++;setRows([]);let active=true;platform.getState({key:'watch:'+preferences.deviceId}).then(v=>{if(active)setWatch({...defaultWatch,...v.value});}).catch(e=>setError(errorText(e)));refresh();return()=>{active=false;selection.current++;};},[ready,preferences.source,preferences.deviceId]);
 useEffect(()=>{if(!ready)return;const timer=setInterval(()=>{setClock(Date.now());if(!document.hidden)refresh();},2000);return()=>clearInterval(timer);},[ready]);
 useEffect(()=>{if(!ready||!preferences.running||preferences.source!=='simulation')return;const tick=async()=>{if(document.hidden||demoBusy.current)return;demoBusy.current=true;try{await platform.appendDemo({payload:domain.syntheticSample(current.current.scenario,step.current++)});await persist('v2-demo-step',step.current);await refresh();}catch(e){setError(errorText(e));}finally{demoBusy.current=false;}};tick();const timer=setInterval(tick,2000);return()=>clearInterval(timer);},[ready,preferences.running,preferences.scenario,preferences.source]);
 const select=(source:Source,deviceId?:string)=>{selection.current++;setRows([]);setPreferences(p=>({...p,source,deviceId:deviceId??(source==='simulation'?'demo-station':stations[0]?.deviceId??'riverguard-01')}));};
 const saveWatch=async(value:Watch)=>{await persist('watch:'+preferences.deviceId,value);setWatch(value);};
 return {ready,preferences,setPreferences,select,rows,stations,receiver,monitoring,watch,saveWatch,error,setError,total,refresh,clock,evaluation:domain.evaluate(rows,watch,clock)};
}
export type Monitor=ReturnType<typeof useMonitor>;
