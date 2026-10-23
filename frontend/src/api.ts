let csrf='';
export class ApiError extends Error { status:number; retryAfter:number; constructor(message:string,status:number,retryAfter=0){super(message);this.status=status;this.retryAfter=retryAfter;} }
export function setCsrf(value:string){csrf=value||'';}
export async function api<T=any>(path:string, options:RequestInit={}):Promise<T>{
  const response=await fetch('/api/ui'+path,{...options,credentials:'same-origin',headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{}),...options.headers}});
  if(!response.ok){let message='Something went wrong. Please try again.';try{const data=await response.json();const detail=data.detail??data.error??data.message;message=typeof detail==='string'?detail:detail?.message??(Array.isArray(detail)?detail.map((e:any)=>e.msg).join(' · '):message);}catch{/* keep safe fallback */}throw new ApiError(message,response.status,Number(response.headers.get('Retry-After')||0));}
  if(response.status===204)return undefined as T;
  return response.json();
}
export const post=<T=any>(path:string,body:unknown={})=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const put=<T=any>(path:string,body:unknown)=>api<T>(path,{method:'PUT',body:JSON.stringify(body)});
export const patch=<T=any>(path:string,body:unknown)=>api<T>(path,{method:'PATCH',body:JSON.stringify(body)});
export const query=(values:Record<string,unknown>)=>new URLSearchParams(Object.fromEntries(Object.entries(values).filter(([,v])=>v!==undefined&&v!==null&&v!=='').map(([k,v])=>[k,String(v)]))).toString();
export const time=(v:unknown,short=true)=>!v?'—':new Intl.DateTimeFormat('en-MY',{timeZone:'Asia/Kuala_Lumpur',...(short?{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}:{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false})}).format(new Date(typeof v==='number'&&v<1e12?v*1000:v as string));
export const err=(e:unknown)=>e instanceof Error?e.message:'Something went wrong. Please try again.';
export function age(seconds:unknown){if(typeof seconds!=='number'||!Number.isFinite(seconds))return 'Unknown';const n=Math.max(0,Math.round(seconds));if(n<60)return `${n}s ago`;if(n<3600)return `${Math.floor(n/60)}m ${n%60}s ago`;if(n<86400)return `${Math.floor(n/3600)}h ${Math.floor(n%3600/60)}m ago`;return `${Math.floor(n/86400)}d ${Math.floor(n%86400/3600)}h ago`;}
export function requestId(){if(typeof crypto.randomUUID==='function')return crypto.randomUUID();const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const h=[...bytes].map(n=>n.toString(16).padStart(2,'0'));return `${h.slice(0,4).join('')}-${h.slice(4,6).join('')}-${h.slice(6,8).join('')}-${h.slice(8,10).join('')}-${h.slice(10).join('')}`;}
export function saveFile(name:string,content:string,type='text/plain'){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
