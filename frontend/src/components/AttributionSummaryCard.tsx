import { ArrowUpRight } from "lucide-react";
import type { SnapshotAttribution, SnapshotAttributionInstrument } from "../lib/api";
import { formatSnapshotDateIso } from "../lib/api";
import { formatOrderDate, signedGbp } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { AttributionWaterfall } from "./AttributionWaterfall";

export function AttributionSummaryCard({
  attribution,
  search = "",
  selectedComparison = false,
  compact = false,
}: {
  attribution: SnapshotAttribution | null;
  search?: string;
  selectedComparison?: boolean;
  compact?: boolean;
}) {
  if (!attribution) return null;
  const available =
    attribution.opening_value_gbp != null &&
    attribution.closing_value_gbp != null &&
    attribution.residual_market_movement_gbp != null;
  const comparison =
    attribution.from_batch && attribution.to_batch
      ? `from=${attribution.from_batch.id}&to=${attribution.to_batch.id}`
      : null;
  const href = comparison
    ? scopedNavigationUrl(`/activity?tab=changes&${comparison}`, search)
    : null;
  const dateLabel = compact ? formatOrderDate : formatSnapshotDateIso;
  const unavailableReason = !available
    ? attribution.notes[attribution.notes.length - 1]
    : undefined;
  const carriedForward = attribution.notes.some((note) =>
    note.startsWith("Some account valuations are carried forward at these boundaries;"),
  );
  const unlinked = attribution.notes
    .map((note) => note.match(/^(\d+) flow order\(s\) were not linked to an instrument;/)?.[1])
    .find(Boolean);

  const allMoves = [...attribution.top_contributors, ...attribution.top_detractors].map((r) =>
    Math.abs(r.estimated_market_movement_gbp),
  );
  const maxMove = Math.max(1, ...allMoves);

  const movers = (title: string, rows: SnapshotAttributionInstrument[]) => (
    <div className="min-w-0">
      <h3 className="tufte-label mb-1.5">{title}</h3>
      {rows.length ? (
        <ul className="divide-y divide-white/[0.05]">
          {rows.slice(0, 3).map((row) => {
            const params = new URLSearchParams(comparison ?? "");
            params.set("account", row.account_name);
            params.set("inst", String(row.instrument_id));
            const pos = row.estimated_market_movement_gbp >= 0;
            const barW = Math.max(4, (Math.abs(row.estimated_market_movement_gbp) / maxMove) * 100);
            return (
              <li key={row.instrument_id}>
                <a
                  className="-mx-1.5 flex items-center justify-between gap-2.5 px-1.5 py-1.5 text-xs transition-colors hover:bg-white/[0.03] focus-visible:outline"
                  href={scopedNavigationUrl(`/activity?tab=changes&${params}`, search)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="num text-[11px] font-semibold text-white">{row.identifier}</span>
                      <span className="text-[10px] text-slate-500">{row.account_name}</span>
                    </div>
                    <p
                      className="truncate text-[11px] text-slate-400"
                      title={`${row.security_name} · ${row.identifier} · ${row.account_name}`}
                    >
                      {row.security_name}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <div className="hidden h-1.5 w-12 bg-white/[0.05] sm:block" aria-hidden="true">
                      <div
                        className={`h-full ${pos ? "bg-emerald-400/75" : "bg-rose-400/75"}`}
                        style={{ width: `${barW}%` }}
                      />
                    </div>
                    <span
                      className={`num w-16 text-right font-medium ${pos ? "text-pos" : "text-neg"}`}
                    >
                      {signedGbp(row.estimated_market_movement_gbp)}
                    </span>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-slate-500">None in this comparison</p>
      )}
    </div>
  );

  return (
    <section className="min-w-0" aria-labelledby="attribution-title">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <h2 id="attribution-title" className="tufte-label text-slate-200">
            What changed
          </h2>
          <p className="num mt-0.5 text-[11px] text-slate-500">
            {selectedComparison
              ? "Selected comparison"
              : compact
                ? "Latest snapshots"
                : "Latest comparison"}
            {attribution.from_batch && attribution.to_batch
              ? ` · ${dateLabel(attribution.from_batch.as_of_date)} – ${dateLabel(attribution.to_batch.as_of_date)}`
              : ""}
          </p>
        </div>
        {(href || compact) && (
          <a
            href={href ?? scopedNavigationUrl("/activity?tab=changes", search)}
            className="action-link shrink-0"
          >
            Full snapshot changes <ArrowUpRight size={11} aria-hidden="true" />
          </a>
        )}
      </div>

      {available ? (
        <>
          <AttributionWaterfall attribution={attribution} compact={compact} />
          <div className="mt-4 space-y-3.5 border-t border-white/[0.08] pt-3.5">
            {movers("Top contributors", attribution.top_contributors)}
            {movers("Top detractors", attribution.top_detractors)}
          </div>
        </>
      ) : (
        <p className="mt-3 text-xs text-amber-200">Attribution unavailable</p>
      )}

      {attribution.unallocated_residual_gbp != null &&
        Math.abs(attribution.unallocated_residual_gbp) >= 0.005 && (
          <p className="mt-2 text-xs text-amber-200">
            Unallocated residual adjustment: {signedGbp(attribution.unallocated_residual_gbp)}.
            {!compact && " Instrument estimates alone do not sum to the portfolio residual."}
          </p>
        )}
      {!compact && (
        <div className="mt-3 space-y-1.5">
          {attribution.notes.map((note) => (
            <p key={note} className="text-xs text-slate-400">
              {note}
            </p>
          ))}
        </div>
      )}
      {compact && !available && unavailableReason && (
        <p className="mt-1 text-xs text-slate-400">{unavailableReason}</p>
      )}
      {compact && available && (carriedForward || unlinked) && (
        <ul className="mt-2 space-y-1 text-xs text-amber-200">
          {carriedForward && <li>Some account values were carried forward.</li>}
          {unlinked && (
            <li>
              {unlinked} {unlinked === "1" ? "unlinked order is" : "unlinked orders are"} not allocated to holdings.
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
