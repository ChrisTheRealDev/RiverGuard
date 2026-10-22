import {useEffect,useRef,useState} from 'react';
import {platform,persist,errorText,type Source,type RecordRow,type Station,type Receiver,type Monitoring,type WatchRecord,type WatchSettings,type DemoState} from './platform';
import './domain.js';
export const domain=globalThis.RiverGuardDomain;
export type Watch=WatchSettings;
export const defaultWatch:Watch={elevated:70,warning:100,rise_limit:10};
export const scenarios=['Normal river','Cloudier water','Sudden change','Rising water level'];
type Preferences={source:Source;deviceId:string};
const initial:Preferences={source:'simulation',deviceId:'demo-station'};
export function useMonitor(){
 const [ready,setReady]=useState(false),[preferences,setPreferences]=useState(initial),[rows,setRows]=useState<RecordRow[]>([]),[stations,setStations]=useState<Station[]>([]),[receiver,setReceiver]=useState<Receiver>({running:false,enabled:false,port:8000,addresses:[]}),[monitoring,setMonitoring]=useState<Monitoring>({running:false,enabled:false,notificationsAllowed:false}),[watchRecord,setWatchRecord]=useState<WatchRecord|null>(null),[alertState,setAlertState]=useState<Awaited<ReturnType<typeof platform.getAlertState>>['conditions']>([]),[watchError,setWatchError]=useState(''),[readError,setReadError]=useState(''),[demoError,setDemoError]=useState(''),[demo,setDemo]=useState<DemoState|null>(null),[demoBusy,setDemoBusy]=useState(false),[total,setTotal]=useState(0),[clock,setClock]=useState(Date.now());
 const current=useRef(preferences),selection=useRef(0),requests=useRef(0),inFlight=useRef<number|null>(null);current.current=preferences;
 const refresh=async()=>{
  const p=current.current,scope=selection.current;if(inFlight.current===scope)return;inFlight.current=scope;const request=++requests.current;
  const result=await Promise.allSettled([platform.listStations(),platform.listReadings({...p,limit:120}),platform.getMonitoring(),platform.getWatch(p),platform.getDemo(),platform.getAlertState(p)]);
  if(inFlight.current===scope)inFlight.current=null;if(scope!==selection.current||request!==requests.current)return;
  const [list,readings,status,policy,simulation,alerts]=result;
  if(list.status==='fulfilled'){setStations(list.value.items);setReceiver(list.value.receiver);}
  if(readings.status==='fulfilled'){setRows(readings.value.items);setTotal(readings.value.total);}
  if(status.status==='fulfilled')setMonitoring(status.value);
  if(alerts.status==='fulfilled')setAlertState(alerts.value.conditions);
  const failed=[list,readings,status,alerts].find(r=>r.status==='rejected');setReadError(failed?.status==='rejected'?errorText(failed.reason):'');
  if(policy.status==='fulfilled'){setWatchRecord(policy.value);setWatchError('');}else{setWatchRecord(null);setWatchError('Thresholds unavailable. '+errorText(policy.reason));}
  if(simulation.status==='fulfilled'){setDemo(simulation.value);setDemoError(simulation.value.error??'');}else setDemoError(errorText(simulation.reason));
 };
 useEffect(()=>{let active=true;(async()=>{try{const saved=(await platform.getState({key:'v2-preferences'})).value;const p:Preferences={source:saved?.source==='esp32'?'esp32':'simulation',deviceId:typeof saved?.deviceId==='string'?saved.deviceId:initial.deviceId};if(p.source==='simulation')p.deviceId='demo-station';if(active){current.current=p;setPreferences(p);setReady(true);}}catch(e){if(active)setReadError(errorText(e));}})();return()=>{active=false;requests.current++;};},[]);
 useEffect(()=>{if(!ready)return;persist('v2-preferences',preferences).catch(e=>setReadError(errorText(e)));},[ready,preferences]);
 useEffect(()=>{if(!ready)return;selection.current++;setRows([]);setTotal(0);setWatchRecord(null);setAlertState([]);setWatchError('');setReadError('');void refresh();return()=>{selection.current++;};},[ready,preferences.source,preferences.deviceId]);
 useEffect(()=>{if(!ready)return;const timer=setInterval(()=>{setClock(Date.now());if(!document.hidden)void refresh();},2000);return()=>clearInterval(timer);},[ready]);
 const select=(source:Source,deviceId?:string)=>{selection.current++;requests.current++;setRows([]);setTotal(0);setWatchRecord(null);setAlertState([]);setWatchError('');const next={source,deviceId:deviceId??(source==='simulation'?'demo-station':stations[0]?.deviceId??'riverguard-01')};current.current=next;setPreferences(next);};
 const updateDemo=async(changes:Partial<Pick<DemoState,'scenario'|'running'>>)=>{if(!demo||demoBusy)return;setDemoBusy(true);try{const result=await platform.saveDemo({expectedRevision:demo.revision,scenario:changes.scenario??demo.scenario,running:changes.running??demo.running});setDemo(result);setDemoError(result.error??'');await refresh();}catch(e){setDemoError(errorText(e));try{setDemo(await platform.getDemo());}catch{}}finally{setDemoBusy(false);}};
 const watch=watchRecord?.settings??defaultWatch,watchReady=Boolean(watchRecord?.valid&&!watchRecord.needsReview);
 const evaluation=domain.evaluate(rows,watch,clock);
 if(!watchReady){evaluation.signals=evaluation.signals.filter(s=>!s.kind.startsWith('water_'));evaluation.rate=null;}
 for(const condition of alertState){if(!evaluation.signals.some(s=>s.kind===condition.kind)){evaluation.signals.push({kind:condition.kind,severity:condition.level>=3?'Warning':condition.level>=2?'Watch':'Review',title:condition.title,explanation:(condition.lastKnown?'Last-known condition; a current clear reading is still needed. ':'')+condition.detail,timestamp:condition.measuredAt,lastKnown:condition.lastKnown});}}
 return {ready,preferences,select,rows,stations,receiver,monitoring,watch,watchRecord,watchReady,watchError,demo,demoBusy,demoError,updateDemo,error:readError||watchError,setError:setReadError,total,refresh,clock,evaluation};
}
export type Monitor=ReturnType<typeof useMonitor>;
