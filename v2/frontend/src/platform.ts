import {Capacitor,registerPlugin} from '@capacitor/core';
export type Field='ph'|'turbidity'|'temperature'|'water_level';
export type Source='simulation'|'esp32';
export type Settings={enabled:Record<Field,boolean>;ph:{mv:number;value:number}[]|null;turbidity:{mv:number;value:number}[]|null;level:{reference:number;minimum:number;maximum:number}|null;temperature_offset:number;verified:boolean};
export type RecordRow={id:number;source:Source;deviceId:string;timestamp:string;receivedAt:string;payload:Record<string,any>;settings:Settings|null};
export type Receiver={running:boolean;enabled:boolean;port:number;addresses:string[];error?:string};
export type Station={deviceId:string;revision:number;acknowledgedRevision:number|null;lastReceived:string|null;lastMeasured:string|null};
export type Monitoring={running:boolean;enabled:boolean;notificationsAllowed:boolean;error?:string};
export type Saved={saved:boolean};
export const fields:Field[]=['ph','turbidity','temperature','water_level'];
export const blank:Settings={enabled:{ph:false,turbidity:false,temperature:false,water_level:false},ph:null,turbidity:null,level:null,temperature_offset:0,verified:false};
export const native=Capacitor.isNativePlatform();
export interface Platform{
 getState(v:{key:string}):Promise<{value:any}>;setState(v:{key:string;value:any}):Promise<Saved>;
 registerStation(v:{deviceId:string;rotate?:boolean}):Promise<{deviceId:string;token:string}>;
 listStations():Promise<{items:Station[];receiver:Receiver}>;
 getSettings(v:{deviceId:string}):Promise<{revision:number;settings:Settings}>;
 saveSettings(v:{deviceId:string;expectedRevision:number;settings:Settings}):Promise<{revision:number;settings:Settings}>;
 listReadings(v:{source:Source;deviceId:string;limit?:number;cursor?:string}):Promise<{items:RecordRow[];nextCursor:string|null;total:number}>;
 appendDemo(v:{payload:any}):Promise<{stored:boolean}>;setReceiver(v:{enabled:boolean}):Promise<Receiver>;
 getMonitoring():Promise<Monitoring>;
 requestNotifications():Promise<Monitoring>;
 exportData(v:{source:Source;deviceId:string}):Promise<Saved>;
 saveText(v:{name:string;mime:string;content:string}):Promise<Saved>;saveGuide():Promise<Saved>;
}
let csrf='';
export class PlatformError extends Error{status:number;constructor(message:string,status:number){super(message);this.status=status;}}
export const errorText=(e:unknown)=>e instanceof Error?e.message:'Something went wrong. Your saved readings are still here.';
export async function request<T=any>(path:string,body?:unknown):Promise<T>{const r=await fetch('/api/v2'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...(csrf?{'X-CSRF-Token':csrf}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});if(!r.ok){let message='Could not connect. Check that the RiverGuard V2 service is running.';try{const v=await r.json();message=typeof v.detail==='string'?v.detail:typeof v.error==='string'?v.error:typeof v.message==='string'?v.message:message;}catch{}throw new PlatformError(message,r.status);}return r.json();}
export async function session(){if(native)return true;const result=await request<{authenticated:boolean;csrf?:string}>('/session');csrf=result.csrf??'';return result.authenticated;}
export async function signIn(kind:'bootstrap'|'pair',value:string){await request('/'+kind,{[kind==='pair'?'code':'token']:value});if(!await session())throw new Error('Could not establish this browser session. Start RiverGuard V2 again.');}
export async function download(name:string,content:Blob|string,mime='text/plain'){const url=URL.createObjectURL(content instanceof Blob?content:new Blob([content],{type:mime}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return {saved:true};}
async function exported(method:string,body:unknown={}){const result=await request<any>('/phone/'+method,body);if(result.url){const url=new URL(result.url,location.href);if(url.origin!==location.origin)throw new Error('The export address must stay on this RiverGuard installation.');const r=await fetch(url,{credentials:'same-origin'});if(!r.ok)throw new Error('The download could not be prepared. Try again.');return download(result.name??'RiverGuard-export',await r.blob(),result.mime);}if(typeof result.content==='string')return download(result.name??'RiverGuard-export',result.content,result.mime);return result as Saved;}
const methods=['getState','setState','registerStation','listStations','getSettings','saveSettings','listReadings','appendDemo','setReceiver','getMonitoring'] as const;
const web=Object.fromEntries(methods.map(method=>[method,(body:unknown={})=>request('/phone/'+method,body)])) as unknown as Platform;
web.exportData=v=>exported('exportData',v);web.saveGuide=()=>exported('saveGuide');web.saveText=({name,mime,content})=>download(name,content,mime);
web.requestNotifications=()=>web.getMonitoring();
export const platform:Platform=native?registerPlugin<Platform>('RiverGuardV2'):web;
const writes=new Map<string,Promise<unknown>>();
export function persist(key:string,value:unknown){const next=(writes.get(key)??Promise.resolve()).catch(()=>{}).then(()=>platform.setState({key,value}));writes.set(key,next);return next;}
export const formatTime=(v:string|number|null|undefined)=>v?new Date(v).toLocaleString('en-MY',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}):'No readings yet';
