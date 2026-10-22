import {useEffect,useRef} from 'react';
import type {ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {X,Info,LoaderCircle} from 'lucide-react';

export function Modal({title,children,onClose,className=''}:{title:string;children:ReactNode;onClose:()=>void;className?:string}){
 const ref=useRef<HTMLDivElement>(null);
 const closeRef=useRef(onClose);closeRef.current=onClose;
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;const el=ref.current;const old=document.body.style.overflow;document.body.style.overflow='hidden';el?.focus();
  const key=(e:KeyboardEvent)=>{const dialogs=document.querySelectorAll('.modal');if(dialogs[dialogs.length-1]!==el)return;if(e.key==='Escape'){e.preventDefault();closeRef.current();}if(e.key==='Tab'&&el){const list=[...el.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')].filter(e=>e.offsetParent!==null);if(!list.length){e.preventDefault();return;}const first=list[0],last=list[list.length-1];if(e.shiftKey&&(document.activeElement===first||document.activeElement===el)){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
  document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=old;previous?.focus();};
 },[]);
 return createPortal(<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={'modal '+className}><div className="modal-heading"><h2>{title}</h2><button className="icon-button" aria-label={'Close '+title} onClick={onClose}><X size={20}/></button></div>{children}</div></div>,document.body);
}
export function Help({label,children}:{label:string;children:ReactNode}){return <details className="help"><summary aria-label={'About '+label}><Info size={15}/></summary><div role="note">{children}</div></details>;}
export function Empty({title,children}:{title:string;children:ReactNode}){return <div className="empty-state"><span className="empty-ripple">≈</span><h3>{title}</h3><p>{children}</p></div>;}
export function Busy({text='Loading…'}:{text?:string}){return <div className="loading"><LoaderCircle className="spin" size={18}/><span>{text}</span></div>;}
export function ErrorNote({message}:{message:string}){return message?<div role="alert" className="error-note">{message}</div>:null;}
