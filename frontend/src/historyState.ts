/** A response may only render in the exact view that requested it. */
export function historyScope(source:string,device:string,tab:string,range:string,anchor:number,grouped=true){return JSON.stringify([source,device,tab,...(tab==='readings'?[range,anchor]:tab==='alerts'?[grouped]:[])]);}
export function pageRows<T>(responseScope:string,viewScope:string,items:T[]):T[]{return responseScope===viewScope?items:[];}
export const historyTabs=['readings','alerts','evidence'] as const;
export function historyTabForKey(current:typeof historyTabs[number],key:string){const index=historyTabs.indexOf(current);if(key==='Home')return historyTabs[0];if(key==='End')return historyTabs[historyTabs.length-1];if(key==='ArrowRight')return historyTabs[(index+1)%historyTabs.length];if(key==='ArrowLeft')return historyTabs[(index+historyTabs.length-1)%historyTabs.length];return null;}
