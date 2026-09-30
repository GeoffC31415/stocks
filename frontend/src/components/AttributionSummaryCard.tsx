import type { SnapshotAttribution, SnapshotAttributionInstrument } from "../lib/api";
import { formatSnapshotDateIso } from "../lib/api";
import { signedGbp } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { AttributionWaterfall } from "./AttributionWaterfall";

export function AttributionSummaryCard({ attribution, search = "", selectedComparison = false }: { attribution: SnapshotAttribution | null; search?: string; selectedComparison?: boolean }) {
  if (!attribution) return null;
  const available = attribution.opening_value_gbp != null && attribution.closing_value_gbp != null && attribution.residual_market_movement_gbp != null;
  const comparison = attribution.from_batch && attribution.to_batch
    ? `from=${attribution.from_batch.id}&to=${attribution.to_batch.id}` : null;
  const href = comparison ? scopedNavigationUrl(`/activity?tab=changes&${comparison}`, search) : null;
  const movers = (title: string, rows: SnapshotAttributionInstrument[]) => <div className="min-w-0">
    <h3 className="mb-1 text-xs font-medium text-slate-400">{title}</h3>
    {rows.length ? <ul className="space-y-2">{rows.slice(0, 2).map((row) => {
      const params = new URLSearchParams(comparison ?? "");
      params.set("account", row.account_name); params.set("inst", String(row.instrument_id));
      return <li key={row.instrument_id}>
        <a className="flex min-h-9 items-center justify-between gap-3 rounded text-sm focus-visible:outline" href={scopedNavigationUrl(`/activity?tab=changes&${params}`, search)}>
          <span className="min-w-0 truncate text-cyan-200" title={`${row.security_name} · ${row.identifier} · ${row.account_name}`}>{row.security_name}</span>
          <span className={`tabular whitespace-nowrap ${row.estimated_market_movement_gbp >= 0 ? "text-pos" : "text-neg"}`}>{signedGbp(row.estimated_market_movement_gbp)}</span>
        </a>
      </li>;
    })}</ul> : <p className="text-xs text-slate-400">None in this comparison</p>}
  </div>;
  return <section className="surface-card min-w-0 p-4 sm:p-5" aria-labelledby="attribution-title">
    <h2 id="attribution-title" className="text-base font-semibold">What changed</h2>
    <p className="mt-1 text-xs text-slate-400">{selectedComparison ? "Selected snapshot comparison" : "Latest snapshot comparison"}{attribution.from_batch && attribution.to_batch
      ? ` · ${formatSnapshotDateIso(attribution.from_batch.as_of_date)} – ${formatSnapshotDateIso(attribution.to_batch.as_of_date)}` : ""}</p>
    {available ? <>
      <AttributionWaterfall attribution={attribution} />
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {movers("Top contributors", attribution.top_contributors)}
        {movers("Top detractors", attribution.top_detractors)}
      </div>
    </> : <p className="mt-3 text-sm text-amber-200">Attribution unavailable</p>}
    {attribution.unallocated_residual_gbp != null && Math.abs(attribution.unallocated_residual_gbp) >= 0.005 &&
      <p className="mt-2 text-xs text-amber-200">Unallocated residual adjustment: {signedGbp(attribution.unallocated_residual_gbp)}. Instrument estimates alone do not sum to the portfolio residual.</p>}
    <div className="mt-3 space-y-2">{attribution.notes.map((note) => <p key={note} className="text-xs text-slate-400">{note}</p>)}</div>
    {href && <a href={href} className="mt-3 inline-flex min-h-9 items-center text-sm text-cyan-200 underline">Full snapshot changes</a>}
  </section>;
}
