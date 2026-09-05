import { Link,useLocation } from "react-router-dom";
import { holdingsLink } from "../lib/investigationLinks";
import type { SnapshotAttribution } from "../lib/api";
import { signedGbp, toGbp } from "../lib/formatters";

export function ContributionDetails({ attribution, instrumentId }: { attribution: SnapshotAttribution; instrumentId?: number }) {
  const {search}=useLocation();
  const rows = (attribution.movements ?? []).filter((row) => instrumentId == null || row.instrument_id === instrumentId);
  return <section className="surface-card min-w-0 p-4 sm:p-5">
    <h2 className="text-base font-semibold">Estimated contributions by holding</h2>
    <p className="mt-1 text-xs text-slate-400">Residual movement after recorded flows and reinvestment proxies, not proven pure price effects.</p>
    <p className="mt-1 text-xs text-slate-400">{attribution.percentage_point_reason ?? "Percentage-point attribution is unavailable; no validated additive denominator is defined."}</p>
    {rows.length === 0 ? <p className="mt-3 text-sm text-slate-400">No contribution estimate for this selection. Review the comparison's availability notes.</p>
      : <div role="region" aria-label="Holding contributions" tabIndex={0} className="mt-3 max-w-full overflow-x-auto">
        <table className="w-full text-sm"><thead><tr className="text-xs text-slate-400">
          <th scope="col" className="p-2 text-left">Holding</th>
          {["Opening", "External flows", "DRIP proxy", "Residual movement", "Closing", "Source order IDs"].map((label) => <th key={label} scope="col" className="whitespace-nowrap p-2 text-right">{label}</th>)}
        </tr></thead><tbody>{rows.map((row) => <tr key={row.instrument_id} className="border-t border-white/5">
          <th scope="row" className="min-w-40 p-2 text-left font-normal"><Link aria-label={`Explore ${row.security_name} holding`} className="inline-block max-w-40 break-words text-cyan-200 underline [overflow-wrap:anywhere]" to={holdingsLink(search,{account:row.account_name,instrumentId:row.instrument_id})}>{row.security_name}</Link><span className="block max-w-40 break-words text-xs text-slate-400 [overflow-wrap:anywhere]">{row.identifier} · {row.account_name}</span></th>
          <td className="whitespace-nowrap p-2 text-right tabular">{toGbp(row.opening_value_gbp)}</td>
          <td className="whitespace-nowrap p-2 text-right tabular">{signedGbp(row.net_external_flow_gbp)}</td>
          <td className="whitespace-nowrap p-2 text-right tabular">{signedGbp(row.drip_proxy_gbp)}</td>
          <td className="whitespace-nowrap p-2 text-right tabular">{signedGbp(row.estimated_market_movement_gbp)}</td>
          <td className="whitespace-nowrap p-2 text-right tabular">{toGbp(row.closing_value_gbp)}</td>
          <td className="p-2 text-right text-xs text-slate-400">{row.source_order_ids?.join(", ") || "None linked in window"}</td>
        </tr>)}</tbody></table>
      </div>}
    {attribution.unallocated_residual_gbp != null && Math.abs(attribution.unallocated_residual_gbp) >= 0.005 &&
      <p className="mt-3 text-sm text-amber-200">Unallocated portfolio residual adjustment: {signedGbp(attribution.unallocated_residual_gbp)}. This includes flows not assignable to boundary holdings.</p>}
  </section>;
}
