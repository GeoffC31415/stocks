import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TimelineEvents } from '../TimelineEvents';
vi.mock('../../state/useTimeline',()=>({useTimeline:()=>({data:{event_count:2,counts_by_kind:{},notes:[],events:[{id:'one',date:'2026-09-01',kind:'trade',title:'Trade one'},{id:'two',date:'2026-09-02',kind:'trade',title:'Trade two'}]},isLoading:false,isError:false})}));
import { HoldingDetailPanel } from '../HoldingDetailPanel';
afterEach(()=>vi.unstubAllGlobals());
it('keeps actual populated TimelineEvents closed dates in drawer tab order',()=>{
 vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:()=>{},removeEventListener:()=>{}}));
 const {container}=render(<MemoryRouter><HoldingDetailPanel instrumentId={1} onClose={()=>{}}><TimelineEvents instrumentId={1}/></HoldingDetailPanel></MemoryRouter>);
 const summaries=container.querySelectorAll('summary'); expect(summaries).toHaveLength(2);
 expect(container.querySelector('details[open]')).toBeNull();
 const close=screen.getByRole('button',{name:'Close instrument detail'});
 close.focus();fireEvent.keyDown(close,{key:'Tab',shiftKey:true});expect(summaries[1]).toHaveFocus();
 fireEvent.keyDown(summaries[1],{key:'Tab'});expect(close).toHaveFocus();
 const filters=screen.getAllByRole('checkbox');filters[filters.length-1].focus();
 expect(fireEvent.keyDown(filters[filters.length-1],{key:'Tab'})).toBe(true);
});
it('traps at closed timeline summaries rather than filters or hidden descendants',()=>{
 vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:()=>{},removeEventListener:()=>{}}));
 render(<HoldingDetailPanel instrumentId={1} onClose={()=>{}}>
  <input type="checkbox" aria-label="Trades" />
  <details><summary>Timeline day one</summary><button>Hidden event</button></details>
  <details><summary>Timeline day two</summary><a href="#event">Hidden link</a></details>
  <button disabled>Disabled</button><fieldset disabled><button>Disabled by fieldset</button></fieldset>
  <div hidden><button>Hidden</button></div><div style={{display:'none'}}><button>CSS hidden</button></div>
  <div inert><button>Inert</button></div><button tabIndex={-1}>Programmatic only</button>
 </HoldingDetailPanel>);
 const close=screen.getByRole('button',{name:'Close instrument detail'});
 const last=screen.getByText('Timeline day two');
 close.focus(); fireEvent.keyDown(close,{key:'Tab',shiftKey:true}); expect(last).toHaveFocus();
 fireEvent.keyDown(last,{key:'Tab'}); expect(close).toHaveFocus();
 const filter=screen.getByRole('checkbox'); filter.focus();
 expect(fireEvent.keyDown(filter,{key:'Tab'})).toBe(true); expect(filter).toHaveFocus();
});
