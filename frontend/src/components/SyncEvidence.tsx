import type { SyncReport, SyncSection } from '../lib/api';
export function refreshOutcome(report: unknown): string {
 const value=(report as SyncReport | null)?.outcome;
 return value && ['complete','partial','failed','no_op','disabled'].includes(value) ? value : 'unreported';
}
export function SyncEvidence({report,compact=false}:{report?:unknown;compact?:boolean}) {
 const data=report as SyncReport | null;
 const outcome=refreshOutcome(data);
 const byProvider = new Map<string, Map<string, SyncSection>>();
 // Freshness is retained authoritative observation state, not just this run's steps.
 for (const [provider, sections] of Object.entries(data?.freshness ?? {})) {
  byProvider.set(provider, new Map(Object.entries(sections)));
 }
 for (const step of data?.steps ?? []) {
  const sections = byProvider.get(step.name) ?? new Map<string, SyncSection>();
  for (const [section, evidence] of Object.entries(step.sections ?? {})) {
   if (!sections.has(section)) sections.set(section, evidence);
  }
  byProvider.set(step.name, sections);
 }
 const rows = [...byProvider].flatMap(([provider, sections]) =>
  [...sections].map(([section, evidence]) => ({name: `${provider} / ${section}`, evidence})));
 const date=(value:string|null|undefined)=>value || 'Not reported';
 return <div aria-label="Refresh evidence" className="space-y-2 break-words text-xs text-slate-300">
  <p>Refresh outcome: {outcome}</p>
  {!compact && <><p>Successful checks do not prove a new valuation or complete transaction coverage.</p>
  <p>Coverage describes the retained verified observation; current status and reason may report a newer failed attempt.</p>
  {rows.length ? <ul className="space-y-2">{rows.map(({name,evidence:row})=><li key={name}><p className="font-medium">{name}: {row.status??'Unreported'}</p><p>Checked: {date(row.verified_at)}</p><p>Valuation: {date(row.valuation_at)}</p><p>Attempt: {date(row.last_attempt_at)}</p><p>Coverage: {row.coverage??'unknown'}</p><p>Reason: {row.reason_code??'Not reported'}</p><p>Action: {row.action_code??'Not reported'}</p></li>)}</ul>:<p>Per-section checked, valuation, attempt and coverage evidence is not reported by this server.</p>}</>}
 </div>;
}
