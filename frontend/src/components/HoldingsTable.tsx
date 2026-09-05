import type { AllocationTargets } from '../lib/allocationTargetsApi';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { AllocationRow, Instrument } from '../lib/api';
import { toGbp } from '../lib/formatters';
import { filterHoldings, holdingDisplayName, holdingSorts, sortHoldings, type HoldingSort } from '../lib/holdingsView';
import { holdingPerformanceSignals } from './holdingSignals';
type SavedView = {version?: number; sort?: HoldingSort; direction?: 'asc'|'desc'; classification?: boolean};
export function HoldingsTable({ instruments, selectedId, onSelect, scopeTotalValue, targetDrift }: {
 instruments: Instrument[]; groups: AllocationRow[]; selectedId: number|null; onSelect:(id:number|null)=>void; scopeTotalValue?: number|null; targetDrift?: AllocationTargets;
}) {
 const [params,setParams]=useSearchParams();
 const [saved,setSaved]=useState<SavedView>(()=>{try{const s=JSON.parse(localStorage.getItem('holdings-view-v1') ?? 'null');return s?.version===1?s:{};}catch{return {};}});
 const rawSort=params.get('sort') ?? saved.sort ?? 'value';
 const sort=holdingSorts.includes(rawSort as HoldingSort)?rawSort as HoldingSort:'value';
 const direction=(params.get('direction') ?? saved.direction)==='asc'?'asc':'desc';
 const classification=saved.classification===true;
 const filtered=filterHoldings(instruments,params);
 const invalidSort=params.getAll('sort').length>1 || params.getAll('direction').length>1 || (params.has('sort')&&!holdingSorts.includes(rawSort as HoldingSort)) || (params.has('direction')&&!['asc','desc'].includes(params.get('direction')!));
 const rows=invalidSort?[]:sortHoldings(filtered.rows,sort,direction);
 const error=filtered.error ?? (invalidSort?'Invalid holdings sort. Reset view to continue.':null);
 const save=(s:SavedView)=>{setSaved(s);try{localStorage.setItem('holdings-view-v1',JSON.stringify(s));}catch{/* Storage may be disabled. */}};
 const headers:[HoldingSort,string][]=[['security','Security'],['account','Account'],['value','Value'],['weight','Weight'],['pnl','Gain / loss'],['delta','Recent change']];
 const changeSort=(key:HoldingSort)=>{const dir=sort===key&&direction==='desc'?'asc':'desc';save({...saved,version:1,sort:key,direction:dir});const next=new URLSearchParams(params);next.set('sort',key);next.set('direction',dir);setParams(next,{replace:true});};
 return <div className="glass min-w-0 max-w-full rounded-2xl">
  <div className="flex flex-wrap gap-3 p-4">
   <input type="search" aria-label="Search holdings" placeholder="Search ticker, name or identifier" className="min-w-0 rounded bg-slate-900 p-2" value={params.get('q') ?? ''} onChange={e=>{const next=new URLSearchParams(params);next.set('q',e.target.value);setParams(next,{replace:true});}}/>
   <label><input type="checkbox" checked={classification} onChange={e=>save({...saved,version:1,classification:e.target.checked})}/> Classification columns</label>
   <button type="button" onClick={()=>{save({version:1});const next=new URLSearchParams(params);next.delete('sort');next.delete('direction');setParams(next,{replace:true});}}>Reset view</button>
  </div>
  {error&&<p role="alert" className="p-4">{error}</p>}
  <p className="px-4 text-xs text-slate-400">Weight uses the full account scope, including cash. Gain / loss is against book cost; recent change is value change since the previous snapshot, not investment return.</p>
  <p id="holdings-scroll-hint" className="px-4 py-2 text-xs text-slate-400">Scroll horizontally for all columns.</p>
  <div role="region" aria-label="Holdings table" aria-describedby="holdings-scroll-hint" tabIndex={0} className="h-[560px] max-w-full overflow-auto rounded-b-2xl">
   <table className="w-full text-sm"><thead className="sticky top-0 bg-slate-950"><tr>
    {headers.map(([key,label])=><th key={key} scope="col" className={`px-4 py-3 ${key==='security'||key==='account'?'text-left':'text-right'}`} aria-sort={sort===key?direction==='asc'?'ascending':'descending':'none'}><button type="button" className="whitespace-nowrap" onFocus={e=>e.currentTarget.scrollIntoView?.({block:"nearest",inline:"nearest"})} onClick={()=>changeSort(key)}>{label}</button></th>)}
    {classification&&<th scope="col">Classification</th>}
   </tr></thead><tbody>{rows.map(i=><tr key={i.id} className={`border-t border-white/5 ${selectedId===i.id?'bg-cyan-500/10':''}`}>
    <td className="px-4 py-3"><button type="button" data-holding-id={i.id} onFocus={e=>e.currentTarget.scrollIntoView?.({block:"nearest",inline:"nearest"})} aria-label={`View ${holdingDisplayName(i)} in ${i.account_name}`} aria-pressed={selectedId===i.id} onClick={()=>onSelect(selectedId===i.id?null:i.id)} className="max-w-40 break-words text-left font-medium text-white [overflow-wrap:anywhere]">{holdingDisplayName(i)}</button><div className="max-w-56 truncate text-xs text-slate-400" title={i.security_name}>{i.security_name}</div>
     {!i.is_cash&&holdingPerformanceSignals({latestPctChange:i.latest_pct_change,drawdownFromPeakPct:i.drawdown_from_peak_pct,quantityUnchangedSnapshotCount:i.quantity_unchanged_snapshot_count}).map(b=><span key={b.label} className="block text-xs text-slate-400">{b.label}</span>)}
     {!i.is_cash && targetDrift?.status==='available' && targetDrift.groups.filter(g=>g.instrument_ids.includes(i.id) && g.within_tolerance===false && [g.actual_value_gbp,g.actual_weight_pct,g.target_weight_pct,g.drift_pp,g.gap_gbp].every(v=>typeof v==='number'&&Number.isFinite(v))).map(g=><span key={g.group_id} aria-label={`${g.name} target drift`} className="block text-xs text-slate-400">{g.name}: gap {g.gap_gbp!>0?'+':''}{toGbp(g.gap_gbp)} · drift {g.drift_pp!>0?'+':''}{g.drift_pp!.toFixed(1)} pp</span>)}
    </td>
    <td className="px-4 py-3">{i.account_name}</td><td className="tabular px-4 py-3 text-right">{toGbp(i.latest_value_gbp)}</td>
    <td className="tabular px-4 py-3 text-right">{scopeTotalValue!=null&&scopeTotalValue>0&&i.latest_value_gbp!=null?`${(i.latest_value_gbp/scopeTotalValue*100).toFixed(1)}%`:'—'}</td>
    <td className="tabular px-4 py-3 text-right">{toGbp(i.pnl_gbp)}</td><td className="tabular px-4 py-3 text-right">{toGbp(i.delta_value_gbp_since_prev_snapshot)}</td>
    {classification&&<td>{[i.asset_class,i.sector,i.region].filter(Boolean).join(' · ')||'Unknown'}</td>}
   </tr>)}{rows.length===0&&<tr><td colSpan={classification?7:6} className="p-6">No instruments match.</td></tr>}</tbody></table>
  </div>
 </div>;
}
