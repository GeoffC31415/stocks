import { Link, useLocation } from "react-router-dom";
import { useTargetDrift } from "../state/useTargetDrift";
import { scopedNavigationUrl } from "../routing";
import { pct, signedGbp, toGbp } from "../lib/formatters";
export function TargetDriftPanel() {
  const {query,tolerance,setTolerance} = useTargetDrift();
  const {search}=useLocation();
  const data=query.data;
  return <section aria-label="Target drift" className="glass min-w-0 rounded-2xl p-5 space-y-3">
    <h2 className="text-lg font-semibold text-white">Target drift</h2>
    <p className="text-sm text-slate-300">Current allocation, not the selected historical period. Groups must form an exclusive, complete target set. Existing overlapping tags are not changed.</p>
    <label className="flex flex-wrap items-center gap-2 text-sm text-slate-300">Symmetric tolerance (percentage points)
      <input aria-label="Target drift tolerance" className="w-24 rounded bg-slate-800 p-2" type="number" min="0" max="100" step="0.1" value={tolerance} onChange={e=>setTolerance(Number(e.target.value))}/>
    </label>
    {query.isError ? <p role="alert">Unable to load target drift. <button onClick={()=>void query.refetch()}>Retry targets</button></p> : !data ? <p role="status">Loading targets…</p> : <>
      <p className="text-sm text-slate-300">{data.cash_policy} Invested {toGbp(data.invested_value_gbp)}; excluded cash {toGbp(data.excluded_cash_gbp)}.</p>
      {data.status==="unavailable" ? <div role="status" className="space-y-2 text-sm text-amber-200">{data.reasons.map(r=><p key={r}>{r}</p>)}<Link className="underline" to={scopedNavigationUrl("/portfolio?tab=groups",search)}>Resolve target configuration</Link></div> : <div className="overflow-auto" role="region" aria-label="Target comparison" tabIndex={0}><table className="w-full text-sm text-slate-300"><thead><tr><th className="text-left p-2">Group</th><th>Actual / target</th><th>Drift (pp)</th><th>GBP gap to target</th><th>Band</th></tr></thead><tbody>{data.groups.map(g=><tr key={g.group_id}><th className="text-left p-2 break-words">{g.name}</th><td className="p-2 min-w-32 tabular">{pct(g.actual_weight_pct)} / {pct(g.target_weight_pct)}<div className="relative h-2 bg-slate-700 mt-2" aria-hidden="true"><span className="absolute h-2 bg-cyan-400" style={{width:`${g.actual_weight_pct}%`}}/><span className="absolute h-3 w-0.5 -top-0.5 bg-white" style={{left:`${g.target_weight_pct}%`}}/></div></td><td className="p-2 text-right tabular">{g.drift_pp?.toFixed(2)}</td><td className="p-2 text-right tabular">{signedGbp(g.gap_gbp)}</td><td className="p-2">{g.within_tolerance ? "Within band" : "Outside personal band"}</td></tr>)}</tbody></table><p className="mt-2 text-xs">Bar: actual; white marker: target. Positive gap means below target. No trade recommendation.</p></div>}
    </>}
  </section>;
}
