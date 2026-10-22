const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {setImmediate:immediate}=require('node:timers/promises');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
function harness(){
 const slots=[],effects=[];let cursor=0,dirty=true,renderFn,props,tree;
 const react={
  useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],value=>{const next=typeof value==='function'?value(slots[i]):value;if(!Object.is(slots[i],next)){slots[i]=next;dirty=true;}}];},
  useRef(initial){const i=cursor++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
  useEffect(effect,deps){const i=cursor++,previous=slots[i];if(!previous||!deps||deps.some((v,j)=>!Object.is(v,previous.deps?.[j]))){slots[i]={deps,cleanup:previous?.cleanup};effects.push(()=>{slots[i].cleanup?.();slots[i].cleanup=effect();});}},
  useId(){return 'test-id';}
 };
 const jsx=(type,props,key)=>({type,key,props:props??{}});
 async function module(file,names,deps={}){
  const {transformWithOxc}=await import('vite');let {code}=await transformWithOxc(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),file);
  code=code.replace(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?/g,(_,what,where)=>{what=what.trim();if(what.startsWith('{'))return 'const '+what.replace(/\s+as\s+/g,':')+'=require('+JSON.stringify(where)+');';if(what.includes(', {')){const [name,rest]=what.split(/,\s*(?=\{)/);return 'const '+name+'=require('+JSON.stringify(where)+').default;const '+rest.replace(/\s+as\s+/g,':')+'=require('+JSON.stringify(where)+');';}if(what.startsWith('* as '))return 'const '+what.slice(5)+'=require('+JSON.stringify(where)+');';return 'const '+what+'=require('+JSON.stringify(where)+').default;';});
  code=code.replace(/import\s+["']([^"']+)["'];?/g,(_,where)=>'require('+JSON.stringify(where)+');').replace(/export\s+default\s+/g,'').replace(/export\s+(?=function|const|class)/g,'');
  code+='\nmodule.exports={'+names.join(',')+'};';
  const exports={};const icons=new Proxy({}, {get:(_,name)=>({name})});
  const context={module:{exports},exports,require(name){if(name==='react')return react;if(name==='react/jsx-runtime')return {jsx,jsxs:jsx,Fragment:'Fragment'};if(name==='lucide-react')return icons;if(name in deps)return deps[name];if(name.endsWith('/monitor'))return {domain:globalThis.RiverGuardDomain};if(name.endsWith('domain.js'))return {};return {default:({children})=>children};},globalThis,structuredClone,Date,Math,Number,Object,Array,Map,Set,JSON,Promise,URL,URLSearchParams,console,document:{hidden:false},window:{scrollTo(){}},setInterval:()=>1,clearInterval(){},setTimeout:()=>1,clearTimeout(){},confirm:()=>true};
  vm.runInNewContext(code,context,{filename:file});return context.module.exports;
 }
 function render(){cursor=0;dirty=false;tree=renderFn(props);for(const run of effects.splice(0))run();}
 return {module,mount(fn,p={}){renderFn=fn;props=p;render();},update(p){props=p;dirty=true;},get value(){return tree;},async flush(){for(let i=0;i<25;i++){if(dirty)render();await immediate();if(!dirty&&!effects.length&&i>2)break;}if(dirty)render();},unmount(){for(const item of slots)item?.cleanup?.();}};
}
function nodes(tree){if(!tree||typeof tree!=='object')return [];if(Array.isArray(tree))return tree.flatMap(nodes);return [tree,...nodes(tree.props?.children)];}
function text(tree){if(tree===null||tree===undefined||typeof tree==='boolean')return '';if(typeof tree!=='object')return String(tree);if(Array.isArray(tree))return tree.map(text).join(' ');return text(tree.props?.children);}
module.exports={harness,deferred,nodes,text};
