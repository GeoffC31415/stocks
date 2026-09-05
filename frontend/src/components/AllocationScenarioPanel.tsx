import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AllocationTargets } from "../lib/allocationTargetsApi";
import { requestJson } from "../lib/api";
import { toGbp, pct } from "../lib/formatters";
import { useTargetDrift } from "../state/useTargetDrift";
export function AllocationScenarioPanel() {
  const {query}=useTargetDrift();
  return <section aria-label="Contribution scenario" className="glass min-w-0 rounded-2xl p-5 space-y-3">
    <h2 className="text-lg font-semibold text-white">Hypothetical contribution</h2>
    <p className="text-sm text-slate-300">Hypothetical contribution; no orders created. Real cash is unchanged. You choose amounts; this is not an allocation recommendation.</p>
    {query.isError ? <p role="alert">Unable to load scenario prerequisites. <button onClick={()=>void query.refetch()}>Retry prerequisites</button></p> : !query.data ? <p role="status">Loading scenario prerequisites…</p> : query.data.status !== "available" ? <p className="text-sm text-amber-200">Configure a valid target set before modelling a contribution.</p> : <ScenarioForm key={JSON.stringify(query.data)} before={query.data} />}
  </section>;
}

function ScenarioForm({before}:{before:AllocationTargets}) {
  const [amount,setAmount]=useState("0");
  const [allocations,setAllocations]=useState<Record<number,string>>({});
  const [submitted,setSubmitted]=useState<string|null>(null);
  const result=useQuery({queryKey:["allocation-scenario",before.account_name,before.tolerance_pp,JSON.stringify(before),submitted],enabled:submitted!==null,
    queryFn:()=>{
      const p=new URLSearchParams({scenario:submitted!,tolerance_pp:String(before.tolerance_pp)});
      if(before.account_name) p.set("account_name",before.account_name);
      return requestJson<{before:AllocationTargets;after:AllocationTargets;assumption:string}>(`/api/portfolio/allocation-scenario?${p}`,{method:"GET"});
    },retry:false});
  const reset=()=>{setAmount("0");setAllocations({});setSubmitted(null);};
  return <form className="space-y-3 text-sm text-slate-300" onSubmit={e=>{e.preventDefault();setSubmitted(JSON.stringify({contribution_gbp:Number(amount),allocations:before.groups.map(g=>({group_id:g.group_id,amount_gbp:Number(allocations[g.group_id]??0)})),cash_policy:"excluded"}));}}>
    <label className="flex flex-wrap items-center gap-3">Contribution (GBP)<input className="w-36 bg-slate-800 rounded p-2" type="number" min="0" max="1000000000000" step="0.01" required value={amount} onChange={e=>{setAmount(e.target.value);setSubmitted(null);}}/></label>
    <div className="flex flex-wrap gap-4">{before.groups.map(g=><label key={g.group_id} className="flex min-w-0 flex-wrap items-center gap-2"><span className="break-words">{g.name} allocation (GBP)</span><input className="w-32 rounded bg-slate-800 p-2" type="number" min="0" max="1000000000000" step="0.01" required value={allocations[g.group_id]??"0"} onChange={e=>{setAllocations({...allocations,[g.group_id]:e.target.value});setSubmitted(null);}}/></label>)}</div>
    <div className="flex flex-wrap gap-3"><button type="submit" className="btn-primary min-h-11 px-4">Calculate scenario</button><button type="button" className="min-h-11 border border-white/20 rounded px-4" onClick={reset}>Reset scenario</button></div>
    {submitted!==null && (result.isError ? <p role="alert">{result.error.message} <button type="button" onClick={()=>void result.refetch()}>Retry scenario</button></p> : !result.data ? <p role="status">Calculating scenario…</p> : <div role="region" aria-label="Scenario results" className="overflow-auto" tabIndex={0}><p>{result.data.assumption}</p><p>Invested value: {toGbp(result.data.before.invested_value_gbp)} → {toGbp(result.data.after.invested_value_gbp)}. Real cash remains {toGbp(result.data.after.excluded_cash_gbp)}.</p><table aria-label="Before and hypothetical after" className="w-full text-sm"><thead><tr><th className="text-left p-2">Group</th><th>Before value / weight</th><th>After value / weight</th><th>Before → after drift (pp)</th></tr></thead><tbody>{result.data.after.groups.map(g=>{const old=result.data!.before.groups.find(x=>x.group_id===g.group_id)!;return <tr key={g.group_id}><th className="text-left p-2">{g.name}</th><td className="p-2 text-right tabular">{toGbp(old.actual_value_gbp)} / {pct(old.actual_weight_pct)}</td><td className="p-2 text-right tabular">{toGbp(g.actual_value_gbp)} / {pct(g.actual_weight_pct)}</td><td className="p-2 text-right tabular">{old.drift_pp?.toFixed(2)} → {g.drift_pp?.toFixed(2)}</td></tr>;})}</tbody></table></div>)}
  </form>;
}
