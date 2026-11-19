import type { SnapshotAttribution, SnapshotAttributionInstrument } from "../lib/api";
import { formatSnapshotDateIso } from "../lib/api";
import { formatOrderDate, signedGbp } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { AttributionWaterfall } from "./AttributionWaterfall";

export function AttributionSummaryCard({ attribution, search = "", selectedComparison = false, compact = false }: { attribution: SnapshotAttribution | null; search?: string; selectedComparison?: boolean; compact?: boolean }) {
  if (!attribution) return null;
  const available = attribution.opening_value_gbp != null && attribution.closing_value_gbp != null && attribution.residual_market_movement_gbp != null;
  const comparison = attribution.from_batch && attribution.to_batch
    ? `from=${attribution.from_batch.id}&to=${attribution.to_batch.id}` : null;
  const href = comparison ? scopedNavigationUrl(`/activity?tab=changes&${comparison}`, search) : null;
  const dateLabel = compact ? formatOrderDate : formatSnapshotDateIso;
  // Attribution supplies routine methodology first, followed by data-specific notices.
  // In the unavailable response the final note is the specific reason.
  const unavailableReason = !available ? attribution.notes[attribution.notes.length - 1] : undefined;
  const carriedForward = attribution.notes.some((note) => note.startsWith("Some account valuations are carried forward at these boundaries;"));
  const unlinked = attribution.notes.map((note) => note.match(/^(\d+) flow order\(s\) were not linked to an instrument;/)?.[1]).find(Boolean);
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
    <p className="mt-1 text-xs text-slate-400">{selectedComparison ? "Selected snapshot comparison" : compact ? "Latest snapshots" : "Latest snapshot comparison"}{attribution.from_batch && attribution.to_batch
      ? ` · ${dateLabel(attribution.from_batch.as_of_date)} – ${dateLabel(attribution.to_batch.as_of_date)}` : ""}</p>
    {available ? <>
      <AttributionWaterfall attribution={attribution} compact={compact} />
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {movers("Top contributors", attribution.top_contributors)}
        {movers("Top detractors", attribution.top_detractors)}
      </div>
    </> : <p className="mt-3 text-sm text-amber-200">Attribution unavailable</p>}
    {attribution.unallocated_residual_gbp != null && Math.abs(attribution.unallocated_residual_gbp) >= 0.005 &&
      <p className="mt-2 text-xs text-amber-200">Unallocated residual adjustment: {signedGbp(attribution.unallocated_residual_gbp)}.{!compact && " Instrument estimates alone do not sum to the portfolio residual."}</p>}
    {!compact && <div className="mt-3 space-y-2">{attribution.notes.map((note) => <p key={note} className="text-xs text-slate-400">{note}</p>)}</div>}
    {compact && !available && unavailableReason && <p className="mt-1 text-xs text-slate-400">{unavailableReason}</p>}
    {compact && available && (carriedForward || unlinked) && <ul className="mt-2 space-y-1 text-xs text-amber-200">
      {carriedForward && <li>Some account values were carried forward.</li>}
      {unlinked && <li>{unlinked} {unlinked === "1" ? "unlinked order is" : "unlinked orders are"} not allocated to holdings.</li>}
    </ul>}
    {(href || compact) && <a href={href ?? scopedNavigationUrl("/activity?tab=changes", search)} className="mt-3 inline-flex min-h-9 items-center text-sm text-cyan-200 underline">Full snapshot changes</a>}
  </section>;
}
