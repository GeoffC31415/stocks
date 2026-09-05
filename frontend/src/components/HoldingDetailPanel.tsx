import { useEffect, useRef, useState, type ReactNode } from 'react';
export function HoldingDetailPanel({children,onClose,instrumentId}:{children:ReactNode;onClose:()=>void;instrumentId:number}) {
 const panel=useRef<HTMLDivElement>(null);
 const close=useRef<HTMLButtonElement>(null);
 const [narrow,setNarrow]=useState(()=>window.matchMedia?.('(max-width: 1023px)').matches ?? false);
 useEffect(()=>{const mq=window.matchMedia?.('(max-width: 1023px)');if(!mq)return;const update=()=>setNarrow(mq.matches);mq.addEventListener('change',update);return()=>mq.removeEventListener('change',update);},[]);
 useEffect(()=>{
  const previous=document.querySelector<HTMLButtonElement>(`[data-holding-id="${instrumentId}"]`) ?? document.activeElement as HTMLElement;
  close.current?.focus({preventScroll:true});
  return()=>{if(previous?.isConnected)previous.focus({preventScroll:true});};
 },[instrumentId]);
 return <div ref={panel} role={narrow?'dialog':'region'} aria-modal={narrow?true:undefined} aria-label="Instrument detail" className={narrow?'fixed inset-0 z-50 overflow-auto bg-slate-950 p-4':'min-w-0'} onKeyDown={e=>{
  if(e.key==='Escape'){e.preventDefault();onClose();}
  if(narrow&&e.key==='Tab'){
   const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, summary, [tabindex], [contenteditable="true"]') ?? []).filter(node=>{
    if(node.tabIndex<0 || node.matches(':disabled, input[type="hidden"]') || node.closest('[hidden], [inert]'))return false;
    if(node.matches('summary') && node.parentElement?.querySelector('summary')!==node)return false;
    for(let ancestor:HTMLElement|null=node;ancestor;ancestor=ancestor.parentElement){
     const style=getComputedStyle(ancestor);
     if(style.display==='none' || style.visibility==='hidden' || style.visibility==='collapse')return false;
     if(ancestor.matches('details:not([open])')){
      const summary=Array.from(ancestor.children).find(child=>child.tagName==='SUMMARY');
      if(!summary?.contains(node))return false;
     }
    }
    return true;
   }).sort((a,b)=>(a.tabIndex>0?a.tabIndex:Infinity)-(b.tabIndex>0?b.tabIndex:Infinity));
   if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];
   if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
   else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
  }
 }}><button ref={close} type="button" onClick={onClose} className="mb-3 min-h-10 text-cyan-200">Close instrument detail</button>{children}</div>;
}
