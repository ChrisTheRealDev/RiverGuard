import {useCallback,useEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {X,Info,LoaderCircle,Check} from 'lucide-react';

export function Modal({title,children,onClose,className='',exposeClose}:{title:string;children:ReactNode;onClose:()=>void;className?:string;exposeClose?:(close:()=>void)=>void}){
 const ref=useRef<HTMLDivElement>(null);
 const closeRef=useRef(onClose);closeRef.current=onClose;
 const exposeRef=useRef(exposeClose);exposeRef.current=exposeClose;
 const [visible,setVisible]=useState(false);
 const closing=useRef(false);
 const requestClose=useCallback(()=>{if(closing.current)return;closing.current=true;setVisible(false);setTimeout(()=>closeRef.current(),220);},[]);
 useEffect(()=>{const id=setTimeout(()=>setVisible(true),10);exposeRef.current?.(requestClose);return()=>clearTimeout(id);},[requestClose]);
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;const el=ref.current;const old=document.body.style.overflow;document.body.style.overflow='hidden';el?.focus();
  const key=(e:KeyboardEvent)=>{const dialogs=document.querySelectorAll('.modal');if(dialogs[dialogs.length-1]!==el)return;if(e.key==='Escape'){e.preventDefault();requestClose();}if(e.key==='Tab'&&el){const list=[...el.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary,[tabindex="0"]')].filter(e=>e.offsetParent!==null);if(!list.length){e.preventDefault();return;}const first=list[0],last=list[list.length-1];if(e.shiftKey&&(document.activeElement===first||document.activeElement===el)){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
  document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=old;previous?.focus();};
 },[requestClose]);
 return createPortal(<div className={'modal-backdrop'+(visible?' visible':'')} onMouseDown={e=>{if(e.target===e.currentTarget)requestClose();}}><div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={'modal '+className}><div className="modal-heading"><h2>{title}</h2><button className="icon-button" aria-label={'Close '+title} onClick={requestClose}><X size={20}/></button></div>{children}</div></div>,document.body);
}
export function Help({label,children}:{label:string;children:ReactNode}){return <details className="help"><summary aria-label={'About '+label}><Info size={15}/></summary><div role="note">{children}</div></details>;}
export function Empty({title,children}:{title:string;children:ReactNode}){return <div className="empty-state"><span className="empty-ripple">≈</span><h3>{title}</h3><p>{children}</p></div>;}
export function Busy({text='Loading…'}:{text?:string}){return <div className="loading"><LoaderCircle className="spin" size={18}/><span>{text}</span></div>;}
export function ErrorNote({message}:{message:string}){return message?<div role="alert" className="error-note stagger-in">{message}</div>:null;}
export function Toast({message,onDismiss}:{message:string;onDismiss:()=>void}){
 const [visible,setVisible]=useState(false),[shown,setShown]=useState('');
 const dismissRef=useRef(onDismiss);dismissRef.current=onDismiss;
 useEffect(()=>{if(!message){const id=setTimeout(()=>setShown(''),220);setVisible(false);return()=>clearTimeout(id);}setShown(message);const id=setTimeout(()=>setVisible(true),10);return()=>clearTimeout(id);},[message]);
 if(!shown)return null;
 return <div className={'toast'+(visible?' visible':'')} role="status"><Check size={17}/><span>{shown}</span><button className="icon-button" aria-label="Dismiss notification" onClick={()=>dismissRef.current()}><X size={16}/></button></div>;
}
