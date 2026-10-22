/** A response may only render in the exact view that requested it. */
export function historyScope(source:string,device:string,tab:string,range:string,anchor:number,grouped=true){return JSON.stringify([source,device,tab,...(tab==='readings'?[range,anchor]:tab==='alerts'?[grouped]:[])]);}
export function pageRows<T>(responseScope:string,viewScope:string,items:T[]):T[]{return responseScope===viewScope?items:[];}
