import {useEffect,useRef} from 'react';
import type {Overview} from './types';
const colors={ph:'#b9a9ff',turbidity:'#d5bd85',temperature:'#eeac95',water_level:'#7cd9bd'};
let plotly:Promise<any>|undefined;
export default function Chart({data,station}:{data:Overview['chart'];station:string}){
 const element=useRef<HTMLDivElement>(null);
 const latest=useRef({data,station});latest.current={data,station};
 useEffect(()=>{const el=element.current;if(!el)return;let closed=false;let frame=0;
  const draw=async()=>{plotly??=import('plotly.js-basic-dist-min');const module=await plotly;const Plotly=module.default??module;if(closed)return;const {data,station}=latest.current;const points=data.points??[];const color=colors[data.field];let traces:any[]=[];const segments=new Map<string,typeof points>();for(const point of points){const k=String(point.segment??0);if(!segments.has(k))segments.set(k,[]);segments.get(k)!.push(point);}for(const group of segments.values()){const x=group.map(p=>p.timestamp);traces.push({x:[...x,...[...x].reverse()],y:[...group.map(p=>p.max),...[...group].reverse().map(p=>p.min)],type:'scatter',mode:'lines',line:{width:0},fill:'toself',fillcolor:'rgba('+[1,3,5].map(i=>parseInt(color.slice(i,i+2),16)).join(',')+',0.09)',hoverinfo:'skip',showlegend:false});traces.push({x,y:group.map(p=>p.mean),customdata:group.map(p=>[p.min,p.max,p.count]),type:'scatter',mode:'lines',connectgaps:false,line:{color,width:2.5},showlegend:false,hovertemplate:'%{x|%H:%M:%S}<br>Average %{y:.2f} '+data.unit+'<br>Range %{customdata[0]:.2f}–%{customdata[1]:.2f}<extra></extra>'});}
   const localTraces=traces.map(t=>({...t,x:t.x.map((v:string)=>{const date=new Date(v);return new Date(date.getTime()+8*3600000).toISOString().replace('Z','');})}));
   await Plotly.react(el,localTraces,{autosize:true,paper_bgcolor:'transparent',plot_bgcolor:'transparent',margin:{l:48,r:12,t:12,b:32},font:{family:'Inter, Segoe UI, sans-serif',color:'#a9c0c5',size:12},xaxis:{type:'date',tickformatstops:[{dtickrange:[null,60000],value:'%H:%M:%S'},{dtickrange:[60000,null],value:'%H:%M'}],nticks:5,gridcolor:'#a9c0c50c',zeroline:false,fixedrange:false},yaxis:{nticks:5,gridcolor:'#a9c0c51c',zeroline:false,automargin:true},hoverlabel:{bgcolor:'#24424b',bordercolor:'#526e78',font:{color:'#ecf5f4',size:12}},uirevision:station+'-'+data.field,showlegend:false},{displayModeBar:false,responsive:true,scrollZoom:false,displaylogo:false});
  };
  const onUpdate=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(draw);};const resize=new ResizeObserver(onUpdate);resize.observe(el);el.addEventListener('river-update',onUpdate);draw();return()=>{closed=true;resize.disconnect();el.removeEventListener('river-update',onUpdate);cancelAnimationFrame(frame);if(plotly)plotly.then(m=>(m.default??m).purge(el));};
 },[]);
 useEffect(()=>{const el=element.current;if(el){el.dispatchEvent(new Event('river-update'));plotly?.then(async m=>{const Plotly=m.default??m;if(Plotly.Plots&&el.isConnected)Plotly.Plots.resize(el);});}window.dispatchEvent(new Event('resize'));},[data,station]);
 return <div ref={element} className="river-chart" role="img" aria-label={`${data.field} trend in ${data.unit}. Line shows interval averages; shaded band shows the minimum and maximum. Times in Malaysia time.`}/>;
}
