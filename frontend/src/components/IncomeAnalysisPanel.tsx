import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { getIncomeAnalysis, type IncomeDriver } from "../lib/incomeApi";
import { toGbp, signedGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { ordersLink } from "../lib/investigationLinks";
import { MetricCard } from "./MetricCard";

export function IncomeAnalysisPanel() {
  const {accountFilter}=usePreferences();
  const account=accountFilter==="all"?null:accountFilter;
  const [params]=useSearchParams();
  const asOf=params.get("income_as_of");
  const query=useQuery({queryKey:["income",account,asOf],queryFn:()=>getIncomeAnalysis(account,asOf)});
  const data=query.data;
  const purchases=(row:IncomeDriver,prior=false)=>{
    if(row.instrument_id!==null)return ordersLink(params.toString(),{account:row.navigation_account??row.account_name,instrumentId:row.instrument_id,kind:"drip",fromDate:prior?data!.prior_start:data!.current_start,toDate:prior?data!.prior_end:data!.as_of});
    const p=new URLSearchParams(params);p.set("tab","source");p.set("source","order");p.set("record",String(row.order_ids[0]));p.set("account",row.navigation_account??"all");return `/activity?${p}`;
  };
  return <div className="space-y-5 min-w-0">
    <h1 className="text-2xl font-semibold text-white">DRIP purchase proxy</h1>
    <p className="text-sm text-slate-300">Recorded reinvestment purchases, not declared or cash dividends. Import-time classification is retained; the current import threshold never reclassifies historical purchases.</p>
    {query.isError?<p role="alert">Unable to load Income analysis. <button onClick={()=>void query.refetch()}>Retry income</button></p>:!data?<p role="status">Loading Income analysis…</p>:<>
      <section aria-label="Income limitations" className="text-sm text-amber-200 space-y-2">{data.warnings.map(w=><p key={w}>{w}</p>)}</section>
      <p className="text-sm text-slate-300">Recorded transaction coverage: {data.first_transaction_date??"Not recorded"} – {data.latest_transaction_date??"Not recorded"}. Completeness: {data.completeness}.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Current calendar-period purchases" value={toGbp(data.current_recorded_gbp)}><p>{data.current_start} – {data.as_of}</p><p>{data.current_count} recorded proxy purchases</p></MetricCard>
        <MetricCard label="Same period last year" value={toGbp(data.prior_recorded_gbp)}><p>{data.prior_start} – {data.prior_end}</p><p>{data.prior_count} recorded proxy purchases</p></MetricCard>
        <MetricCard label="Recorded-purchase change" value={signedGbp(data.change_gbp)}><p>Not a measured dividend growth rate.</p></MetricCard>
      </div>
      <section className="glass min-w-0 rounded-2xl p-4 space-y-3"><h2 className="text-lg font-semibold">Monthly timing</h2><p className="text-sm text-slate-300">No recorded purchases is shown as a dash, not confirmed zero income. The last month ends on the displayed comparison date in each year.</p><div className="overflow-auto" role="region" aria-label="Monthly proxy results" tabIndex={0}><table aria-label="Monthly recorded reinvestment proxy" className="w-full text-sm text-slate-300"><thead><tr><th className="text-left p-2">Month</th><th>Current period</th><th>Prior period</th></tr></thead><tbody>{data.months.map(m=><tr key={m.month}><th className="text-left p-2">{m.month}</th><td className="text-right tabular p-2">{toGbp(m.current_recorded_gbp)} · {m.current_count} recorded</td><td className="text-right tabular p-2">{toGbp(m.prior_recorded_gbp)} · {m.prior_count} recorded</td></tr>)}</tbody></table></div></section>
      <section className="glass min-w-0 rounded-2xl p-4 space-y-3"><h2 className="text-lg font-semibold">Holding contributions to the change</h2><p className="text-sm text-slate-300">Current/closed status uses the latest snapshot, separately from the comparison dates. Unlinked records remain separate.</p>{data.drivers.length===0?<p>No classified purchases recorded in either comparison period.</p>:<ul className="space-y-3">{data.drivers.map(row=><li key={row.key} className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3"><div className="min-w-0 flex-1 basis-48 [overflow-wrap:anywhere]"><Link className="text-cyan-200 underline" aria-label={`${row.name} matching purchases`} to={purchases(row)}>{row.name}</Link><p className="text-xs text-slate-300">{row.account_name} · {row.holding_status}</p>{row.instrument_id!==null&&<Link className="text-xs text-cyan-200 underline" to={purchases(row,true)}>Prior-period purchases</Link>}</div><div className="text-right text-sm tabular"><p>{toGbp(row.prior_recorded_gbp)} → {toGbp(row.current_recorded_gbp)}</p><p>Change {signedGbp(row.change_gbp)}</p></div></li>)}</ul>}</section>
    </>}
  </div>;
}
