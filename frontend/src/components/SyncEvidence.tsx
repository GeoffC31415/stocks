import type { SyncReport, SyncSection } from '../lib/api';
export function refreshOutcome(report: unknown): string {
 const value=(report as SyncReport | null)?.outcome;
 return value && ['complete','partial','failed','no-op','disabled'].includes(value) ? value : 'unreported';
}
export function SyncEvidence({report,compact=false}:{report?:unknown;compact?:boolean}) {
 const data=report as SyncReport | null;
 const outcome=refreshOutcome(data);
 const raw=data?.sections;
 const rows:SyncSection[]=Array.isArray(raw)?raw:raw&&typeof raw==='object'?Object.entries(raw).map(([name,row])=>({...row,name:row.name??name})):[];
 const date=(value:string|null|undefined)=>value || 'Not reported';
 return <div aria-label="Refresh evidence" className="space-y-2 text-xs text-slate-300">
  <p>Refresh outcome: {outcome}</p>
  {!compact && <><p>Successful checks do not prove a new valuation or complete transaction coverage.</p>
  {rows.length ? <ul className="space-y-2">{rows.map((row,index)=><li key={`${row.name}-${index}`}><p className="font-medium">{row.name??'Section'}: {row.status??'Unreported'}</p><p>Checked: {date(row.checked_at)}</p><p>Valuation: {date(row.valuation_date)}</p><p>Attempt: {date(row.attempted_at)}</p><p>Coverage: {date(row.coverage_start)} – {date(row.coverage_end)}</p>{row.detail && <p>{row.detail}</p>}</li>)}</ul>:<p>Per-section checked, valuation, attempt and coverage dates are not reported by this server.</p>}</>}
 </div>;
}
