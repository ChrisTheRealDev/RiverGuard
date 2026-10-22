import {Capacitor,registerPlugin} from '@capacitor/core';
export type Field='ph'|'turbidity'|'temperature'|'water_level';
export const fields:Field[]=['ph','turbidity','temperature','water_level'];
export type Settings={enabled:Record<Field,boolean>;ph:{mv:number;value:number}[]|null;turbidity:{mv:number;value:number}[]|null;level:{reference:number;minimum:number;maximum:number}|null;temperature_offset:number;verified:boolean};
export type RecordRow={id:number;source:string;deviceId:string;timestamp:string;receivedAt:string;payload:any;settings:Settings|null};
export type Receiver={running:boolean;enabled:boolean;port:number;addresses:string[];error?:string};
export type Station={deviceId:string;revision:number;acknowledgedRevision:number|null;lastReceived:string|null;lastMeasured:string|null};
export const blank:Settings={enabled:{ph:false,turbidity:false,temperature:false,water_level:false},ph:null,turbidity:null,level:null,temperature_offset:0,verified:false};
export const native=Capacitor.isNativePlatform();
interface PhonePlugin{
 getState(v:{key:string}):Promise<{value:any}>;setState(v:{key:string;value:any}):Promise<{saved:boolean}>;
 registerStation(v:{deviceId:string;rotate?:boolean}):Promise<{deviceId:string;token:string}>;
 listStations():Promise<{items:Station[];receiver:Receiver}>;
 getSettings(v:{deviceId:string}):Promise<{revision:number;settings:Settings}>;
 saveSettings(v:{deviceId:string;expectedRevision:number;settings:Settings}):Promise<{revision:number;settings:Settings}>;
 listReadings(v:{source:string;deviceId:string;limit?:number;cursor?:string}):Promise<{items:RecordRow[];nextCursor:string|null;total:number}>;
 appendDemo(v:{payload:any}):Promise<{stored:boolean}>;setReceiver(v:{enabled:boolean}):Promise<Receiver>;
 exportData(v:{source:string;deviceId:string}):Promise<{saved:boolean}>;
 saveText(v:{name:string;mime:string;content:string}):Promise<{saved:boolean}>;
}
const plugin=registerPlugin<PhonePlugin>('RiverGuardPhone');
let database:Promise<IDBDatabase>|undefined;
function open(){return database??=(new Promise((resolve,reject)=>{const r=indexedDB.open('riverguard-phone-preview',1);r.onupgradeneeded=()=>{const db=r.result;db.createObjectStore('state');db.createObjectStore('readings',{keyPath:'id',autoIncrement:true});};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);}));}
async function readState(key:string){const db=await open();return new Promise<any>((resolve,reject)=>{const r=db.transaction('state').objectStore('state').get(key);r.onsuccess=()=>resolve(r.result??null);r.onerror=()=>reject(r.error);});}
async function writeState(key:string,value:any){const db=await open();return new Promise<{saved:boolean}>((resolve,reject)=>{const tx=db.transaction('state','readwrite');tx.objectStore('state').put(value,key);tx.oncomplete=()=>resolve({saved:true});tx.onerror=()=>reject(tx.error);});}
async function previewRows(){const db=await open();return new Promise<RecordRow[]>((resolve,reject)=>{const r=db.transaction('readings').objectStore('readings').getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
async function saveDownload(name:string,content:string,mime:string){const link=document.createElement('a');link.download=name;link.href=URL.createObjectURL(new Blob([content],{type:mime}));link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);return {saved:true};}
const preview:PhonePlugin={
 async getState({key}){return {value:await readState(key)};},setState:({key,value})=>writeState(key,value),
 async registerStation(){throw new Error('Station credentials and live reception are available in the Android APK. This browser preview supports the offline demonstration.');},
 async listStations(){return {items:[],receiver:{running:false,enabled:false,port:8000,addresses:[]}};},
 async getSettings({deviceId}){return await readState('calibration:'+deviceId)??{revision:0,settings:structuredClone(blank)};},
 async saveSettings({deviceId,expectedRevision,settings}){const current=await preview.getSettings({deviceId});if(current.revision!==expectedRevision)throw new Error('Settings changed. Reopen setup before saving.');const v={revision:current.revision+1,settings};await writeState('calibration:'+deviceId,v);return v;},
 async listReadings({source,deviceId,limit=120,cursor}){let rows=(await previewRows()).filter(r=>r.source===source&&r.deviceId===deviceId).sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp)||b.id-a.id);let ceiling=Math.max(0,...rows.map(r=>r.id));let offset=0;if(cursor){const v=JSON.parse(cursor);ceiling=v.ceiling;offset=v.offset;rows=rows.filter(r=>r.id<=ceiling);}const total=rows.length,items=rows.slice(offset,offset+limit);return {items,total,nextCursor:offset+items.length<total?JSON.stringify({ceiling,offset:offset+items.length}):null};},
 async appendDemo({payload}){const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction('readings','readwrite');tx.objectStore('readings').add({source:'simulation',deviceId:'demo-station',timestamp:payload.timestamp,receivedAt:new Date().toISOString(),payload,settings:null});tx.oncomplete=()=>resolve({stored:true});tx.onerror=()=>reject(tx.error);});},
 async setReceiver(){throw new Error('Use the Android APK to receive sensors directly. Browser preview cannot listen for ESP32 packets.');},
 async exportData({source,deviceId}){const rows=(await previewRows()).filter(r=>r.source===source&&r.deviceId===deviceId);return saveDownload('RiverGuard-preview-readings.json',JSON.stringify(rows,null,2),'application/json');},
 async saveText({name,mime,content}){return saveDownload(name,content,mime);}
};
export const phone:PhonePlugin=native?plugin:preview;
export const formatTime=(v:string|number|null|undefined)=>v?new Date(v).toLocaleString('en-MY',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'No readings yet';
