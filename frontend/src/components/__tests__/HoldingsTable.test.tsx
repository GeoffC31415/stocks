import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HoldingsTable } from '../HoldingsTable';
import type { Instrument } from '../../lib/api';
import type { AllocationTargets } from '../../lib/allocationTargetsApi';
const rows = [{id:1,ticker:'AAA',security_name:'Source Alpha',identifier:'source-id',account_name:'ISA',group_ids:[],latest_value_gbp:100,pnl_gbp:-10,latest_pct_change:null,delta_value_gbp_since_prev_snapshot:null}] as unknown as Instrument[];
const target = (gap:number, within_tolerance:boolean|null=false, status:AllocationTargets['status']='available') => ({status,groups:[{group_id:2,name:'Core',instrument_ids:[1],actual_value_gbp:100,actual_weight_pct:20,target_weight_pct:30,drift_pp:gap>0?-10:10,gap_gbp:gap,within_tolerance}]} as AllocationTargets);
it.each([100,-100])('shows backend signed gap %s and drift in a neutral group badge',gap=>{
 render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} targetDrift={target(gap)}/></MemoryRouter>);
 const badge=screen.getByLabelText('Core target drift');
 expect(badge).toHaveTextContent(gap>0?'+£100':'-£100');
 expect(badge).toHaveTextContent(gap>0?'-10.0 pp':'+10.0 pp');
 expect(badge).not.toHaveTextContent(/buy|sell/i);
 expect(badge).toHaveClass('text-slate-400');
});
it.each([undefined,target(100,true),target(100,null),target(100,false,'unavailable'),{...target(100),groups:[]}, {...target(100),groups:[{...target(100).groups[0],gap_gbp:NaN}]}])('suppresses missing, invalid, or in-band targets',targetDrift=>{
 render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} targetDrift={targetDrift}/></MemoryRouter>);
 expect(screen.queryByLabelText('Core target drift')).not.toBeInTheDocument();
});
it('right aligns accessible numeric headers and cells',()=>{
 render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
 for(const name of ['Value','Weight','Gain / loss','Recent change'])expect(screen.getByRole('columnheader',{name})).toHaveClass('text-right');
 const cells=within(screen.getAllByRole('row')[1]).getAllByRole('cell');
 for(const cell of cells.slice(2))expect(cell).toHaveClass('text-right');
});
beforeEach(()=>{ const store = new Map<string,string>(); vi.stubGlobal('localStorage', {getItem:(k:string)=>store.get(k) ?? null, setItem:(k:string,v:string)=>store.set(k,v),removeItem:(k:string)=>store.delete(k)}); });
it('shows scoped weight and accessible selection with source search and sort headers',()=>{
 const select=vi.fn();
 render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={select} scopeTotalValue={1000}/></MemoryRouter>);
 for(const name of ['Security','Account','Value','Weight','Gain / loss','Recent change']) expect(screen.getByRole('button',{name})).toBeInTheDocument();
 expect(screen.getByText('10.0%')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'View AAA in ISA'})); expect(select).toHaveBeenCalledWith(1);
 fireEvent.change(screen.getByRole('searchbox'),{target:{value:'source-id'}}); expect(screen.getByText('10.0%')).toBeInTheDocument();
});
it('uses URL sorting over saved preferences and resets optional columns',()=>{
 localStorage.setItem('holdings-view-v1',JSON.stringify({version:1,sort:'pnl',direction:'asc',classification:true}));
 render(<MemoryRouter initialEntries={['/?sort=value&direction=desc']}><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
 expect(screen.getByRole('columnheader',{name:'Value'})).toHaveAttribute('aria-sort','descending');
 expect(screen.getByRole('checkbox',{name:'Classification columns'})).toBeChecked();
 fireEvent.click(screen.getByRole('button',{name:'Reset view'}));
 expect(screen.getByRole('checkbox',{name:'Classification columns'})).not.toBeChecked();
});
