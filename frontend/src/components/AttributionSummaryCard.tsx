import type { SnapshotAttribution, SnapshotAttributionInstrument } from "../lib/api";
import { formatSnapshotDateIso } from "../lib/api";
import { toGbp } from "../lib/formatters";

const signedGbp = (value: number): string => `${value > 0 ? "+" : ""}${toGbp(value)}`;

export function AttributionSummaryCard({
  attribution,
}: {
  attribution: SnapshotAttribution | null;
}) {
  if (!attribution) return null;

  const marketMovement = attribution.residual_market_movement_gbp;
  const available =
    attribution.opening_value_gbp != null &&
    attribution.closing_value_gbp != null &&
    marketMovement != null;
  const diffHref =
    attribution.from_batch && attribution.to_batch
      ? `/diff?from=${attribution.from_batch.id}&to=${attribution.to_batch.id}`
      : null;

  return (
    <section className="glass rounded-2xl p-5" aria-labelledby="attribution-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            What changed
          </p>
          <h2 id="attribution-title" className="mt-1 text-sm font-semibold text-white">
            {available ? (
              <>
                {toGbp(attribution.opening_value_gbp)} → {toGbp(attribution.closing_value_gbp)}
              </>
            ) : (
              "Attribution unavailable"
            )}
          </h2>
          {attribution.from_batch && attribution.to_batch ? (
            <p className="mt-1 text-xs text-slate-500">
              {formatSnapshotDateIso(attribution.from_batch.as_of_date)} →{" "}
              {formatSnapshotDateIso(attribution.to_batch.as_of_date)}
            </p>
          ) : null}
        </div>
        {diffHref ? (
          <a href={diffHref} className="chip chip-muted">
            Full snapshot changes
          </a>
        ) : null}
      </div>

      {available ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <AttributionStat
              label="Net external flows"
              value={signedGbp(attribution.net_external_flow_gbp ?? 0)}
              detail={`${toGbp(attribution.contributions_gbp)} in · ${toGbp(attribution.withdrawals_gbp)} out`}
            />
            <AttributionStat
              label="DRIP proxy"
              value={toGbp(attribution.drip_proxy_gbp)}
              detail="Internal reinvested income"
            />
            <AttributionStat
              label="Estimated market movement"
              value={signedGbp(marketMovement ?? 0)}
              detail="Residual after observed flows"
              tone={(marketMovement ?? 0) >= 0 ? "pos" : "neg"}
            />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <MoverList title="Top contributors" rows={attribution.top_contributors} />
            <MoverList title="Top detractors" rows={attribution.top_detractors} />
          </div>
        </>
      ) : (
        <p className="mt-3 rounded-xl bg-white/[0.02] p-3 text-xs text-slate-400">
          {attribution.notes[attribution.notes.length - 1] ??
            "Snapshot attribution is not available."}
        </p>
      )}
    </section>
  );
}

function AttributionStat({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "pos" | "neg" | "muted";
}) {
  const toneClass = tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-white";
  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className={`tabular mt-1 text-lg font-semibold ${toneClass}`}>{value}</p>
      <p className="mt-1 text-[11px] text-slate-600">{detail}</p>
    </div>
  );
}

function MoverList({
  title,
  rows,
}: {
  title: string;
  rows: SnapshotAttributionInstrument[];
}) {
  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      {rows.length > 0 ? (
        <div className="space-y-2">
          {rows.slice(0, 3).map((row) => (
            <div
              key={row.instrument_id}
              className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-slate-200">{row.security_name}</p>
                <p className="truncate text-[11px] text-slate-600">
                  {row.identifier} · {row.account_name}
                </p>
              </div>
              <span
                className={`tabular text-xs font-semibold ${
                  row.estimated_market_movement_gbp >= 0 ? "text-pos" : "text-neg"
                }`}
              >
                {signedGbp(row.estimated_market_movement_gbp)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-xl bg-white/[0.02] p-3 text-xs text-slate-600">None</p>
      )}
    </div>
  );
}
