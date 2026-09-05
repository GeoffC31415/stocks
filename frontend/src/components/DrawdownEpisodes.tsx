import { Link, useLocation } from "react-router-dom";
import type { DrawdownEpisode, MetricReason } from "../lib/api";
import { formatOrderDate } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { AnalysisStatus } from "./AnalysisStatus";

export function DrawdownEpisodes({ episodes, available, reasons = [] }: { episodes: DrawdownEpisode[]; available: boolean; reasons?: MetricReason[] }) {
  const location = useLocation();
  return <section className="surface-card min-w-0 p-4 sm:p-5">
    <h2 className="text-base font-semibold">Drawdown episodes</h2>
    <p className="mt-1 text-xs text-slate-400">Measured from the flow-adjusted snapshot index. Recovery is observed between snapshots, not an exact intraday recovery time.</p>
    {!available ? <AnalysisStatus kind="unavailable" title="Drawdown episodes unavailable for this return chain." reasons={reasons} />
      : episodes.length === 0 ? <p className="mt-3 text-sm text-slate-400">No observed drawdown episodes in this window.</p>
      : <div role="region" aria-label="Observed drawdown episodes" tabIndex={0} className="mt-3 max-w-full overflow-x-auto">
        <table className="w-full text-sm"><thead><tr className="text-xs text-slate-400">
          {["Peak / chart window", "Trough", "Depth", "Observed recovery", "Calendar days", "Observations"].map((heading) => <th key={heading} scope="col" className="whitespace-nowrap p-2 text-left">{heading}</th>)}
        </tr></thead><tbody>{episodes.map((episode) => <tr key={episode.id} className="border-t border-white/5">
          <th scope="row" className="p-2 text-left font-normal"><Link className="text-cyan-200 underline" to={`${scopedNavigationUrl(`/portfolio?tab=performance&episode=${encodeURIComponent(episode.id)}`, location.search)}#performance-chart`}>
            View episode from {formatOrderDate(episode.peak_date)}</Link></th>
          <td className="whitespace-nowrap p-2">{formatOrderDate(episode.trough_date)}</td>
          <td className="p-2 text-right tabular text-neg">{episode.depth_pct.toFixed(2)}%</td>
          <td className="min-w-40 p-2 text-xs">{episode.recovery_date
            ? `${formatOrderDate(episode.recovery_interval_start!)} – ${formatOrderDate(episode.recovery_date)}`
            : `Not observed by ${formatOrderDate(episode.end_date)}`}</td>
          <td className="min-w-32 p-2 text-xs tabular">{episode.days_to_trough} to trough · {episode.elapsed_days} elapsed</td>
          <td className="p-2 text-right tabular">{episode.observations}</td>
        </tr>)}</tbody></table>
      </div>}
  </section>;
}
