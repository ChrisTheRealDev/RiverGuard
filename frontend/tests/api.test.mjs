import test from 'node:test';
import assert from 'node:assert/strict';
import {api,post,setCsrf,query,time,requestId,ApiError} from '../src/api.ts';
import {historyScope,pageRows} from '../src/historyState.ts';

test('HTTP-compatible request IDs remain unique UUIDs without crypto.randomUUID',()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'crypto');let serial=0;
 Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues(bytes){for(let i=0;i<bytes.length;i++)bytes[i]=(serial+i)%256;serial++;return bytes;}}});
 try{const ids=Array.from({length:100},requestId);assert.equal(new Set(ids).size,100);assert(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));}finally{Object.defineProperty(globalThis,'crypto',original);}
});
test('mutations carry CSRF header and remain same-origin',async()=>{
 const old=globalThis.fetch;let captured;
 globalThis.fetch=async(url,options)=>{captured={url,options};return new Response(JSON.stringify({ok:true}),{headers:{'Content-Type':'application/json'}});};
 try{setCsrf('test-csrf');assert.deepEqual(await post('/capture',{device_id:'river-1'}),{ok:true});assert.equal(captured.url,'/api/ui/capture');assert.equal(captured.options.credentials,'same-origin');assert.equal(captured.options.headers['X-CSRF-Token'],'test-csrf');}finally{globalThis.fetch=old;setCsrf('');}
});
test('conflicts retain server detail, status and retry delay',async()=>{
 const old=globalThis.fetch;globalThis.fetch=async()=>new Response(JSON.stringify({detail:{message:'Conversation changed in another tab'}}),{status:409,headers:{'Retry-After':'5'}});
 try{await assert.rejects(api('/conversations/example'),e=>e instanceof ApiError&&e.status===409&&e.retryAfter===5&&e.message.includes('another tab'));}finally{globalThis.fetch=old;}
});
test('query encoding does not drop zero or false; display uses MYT',()=>{
 assert.equal(query({limit:0,reset:false,cursor:undefined,device_id:'river 1'}),'limit=0&reset=false&device_id=river+1');assert.match(time('2026-10-21T00:05:06Z'),/08:05:06/);
});
test('switching from reading rows to signals never renders stale reading objects as alerts',()=>{
 const readings=[{id:1,ph:7.1,timestamp:'2026-10-21T00:00:00Z'}];
 const before=historyScope('esp32','station-1','readings','all',100);
 const after=historyScope('esp32','station-1','alerts','all',100);
 assert.deepEqual(pageRows(before,after,readings),[]);
 const signals=[{id:'1:ph',severity:'Review',title:'Acidity outside the reference'}];
 assert.deepEqual(pageRows(after,after,signals),signals);
 assert.deepEqual(pageRows(after,historyScope('esp32','station-2','alerts','all',100),signals),[]);
});

test('episode and individual-sample responses remain isolated during a grouping switch',()=>{
 const episodes=historyScope('esp32','station-1','alerts','all',100,true);
 const samples=historyScope('esp32','station-1','alerts','all',100,false);
 assert.notEqual(episodes,samples);
 assert.deepEqual(pageRows(episodes,samples,[{count:50}]),[]);
});
