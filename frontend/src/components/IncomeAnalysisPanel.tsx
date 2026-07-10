import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Coins, Info } from "lucide-react";
import { api } from "../lib/api";
import { calculateDripAnalysis } from "../lib/dripAnalysis";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";

export function IncomeAnalysisPanel() {
  const { dripThreshold, accountFilter } = usePreferences();
  const accountName = accountFilter === "all" ? undefined : accountFilter;
  const ordersQ = useQuery({
    queryKey: ["orders", dripThreshold, accountFilter],
    queryFn: () => api.getOrders(dripThreshold, accountName),
  });
  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold, accountFilter],
    queryFn: () => api.getOrderPositions(dripThreshold, accountName),
  });
  const analysisAsOf = useMemo(() => new Date(), []);
  const analysis = useMemo(
    () => calculateDripAnalysis(ordersQ.data ?? [], analysisAsOf),
    [analysisAsOf, ordersQ.data],
  );
  const positions = useMemo(
    () => new Map((positionsQ.data ?? []).map((position) => [position.security_name, position])),
    [positionsQ.data],
  );
  const maxYear = Math.max(1, ...analysis.byYear.map((row) => row.total));
  const trailingStart = new Date(
    Date.UTC(
      analysisAsOf.getUTCFullYear() - 1,
      analysisAsOf.getUTCMonth(),
      analysisAsOf.getUTCDate(),
    ),
  );
  const priorStart = new Date(
    Date.UTC(
      analysisAsOf.getUTCFullYear() - 2,
      analysisAsOf.getUTCMonth(),
      analysisAsOf.getUTCDate(),
    ),
  );
  const dateLabel = (date: Date) =>
    date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const topInstruments = analysis.byInstrument.slice(0, 10);
  const otherInstruments = analysis.byInstrument.slice(10);
  const otherTotal = otherInstruments.reduce((sum, row) => sum + row.total, 0);
  const otherCount = otherInstruments.reduce((sum, row) => sum + row.count, 0);

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2">
          <Coins size={18} className="text-amber-300" />
          <h1 className="text-2xl font-semibold text-white">DRIP purchase proxy</h1>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Buys below {toGbp(dripThreshold)} are classified retrospectively as DRIP for the selected account.
        </p>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] px-4 py-3">
        <Info size={15} className="mt-0.5 shrink-0 text-aurora-cyan" />
        <p className="text-xs leading-5 text-slate-400">
          This is a reinvested-income proxy, not a dividend ledger. The source records DRIP purchases but not declared or cash dividends.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Trailing 12 months"
          value={toGbp(analysis.trailing12m)}
          note={`${dateLabel(trailingStart)} – ${dateLabel(analysisAsOf)}`}
          tone="amber"
        />
        <Metric
          label="Previous 12 months"
          value={toGbp(analysis.prior12m)}
          note={`${dateLabel(priorStart)} – ${dateLabel(trailingStart)}`}
        />
        <Metric
          label="12-month change"
          value={analysis.growthPct == null ? "Not available" : `${analysis.growthPct >= 0 ? "+" : ""}${analysis.growthPct.toFixed(1)}%`}
          tone={analysis.growthPct != null && analysis.growthPct >= 0 ? "pos" : "default"}
        />
        <Metric label="All recorded DRIP" value={toGbp(analysis.total)} note={`${analysis.count} purchases`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="glass rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">Annual DRIP proxy</h2>
          <p className="mt-1 text-xs text-slate-500">
            Calendar-year purchases; {analysisAsOf.getUTCFullYear()} is year to date. Display values are rounded.
          </p>
          <div className="mt-4 space-y-3">
            {analysis.byYear.map((row) => (
              <div key={row.year}>
                <div className="flex items-center justify-between text-xs">
                  <span className="tabular text-slate-300">
                    {row.year}{row.year === analysisAsOf.getUTCFullYear() ? " YTD" : ""}
                  </span>
                  <span className="tabular text-amber-200">{toGbp(row.total)} · {row.count}</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-amber-500 to-amber-300"
                    style={{ width: `${(row.total / maxYear) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {analysis.byYear.length === 0 ? (
              <p className="py-8 text-center text-xs text-slate-500">No DRIP-classified orders.</p>
            ) : null}
          </div>
        </section>

        <section className="glass rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">By holding</h2>
          <p className="mt-1 text-xs text-slate-500">Largest recorded reinvestment totals.</p>
          <div className="mt-3 space-y-2">
            {topInstruments.map((row) => {
              const position = positions.get(row.name);
              return (
                <div key={row.name} className="rounded-xl bg-white/[0.02] px-3 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-xs font-medium text-slate-200" title={row.name}>
                      {row.name}
                    </p>
                    <p className="tabular shrink-0 text-xs font-semibold text-amber-200">{toGbp(row.total)}</p>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-600">
                    <span>{row.count} purchases</span>
                    {position?.trailing_drip_yield_pct != null ? (
                      <span>Trailing proxy yield {position.trailing_drip_yield_pct.toFixed(2)}%</span>
                    ) : null}
                  </div>
                </div>
              );
            })}
            {otherInstruments.length > 0 ? (
              <div className="rounded-xl border border-white/[0.05] bg-white/[0.015] px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-medium text-slate-400">
                    Other holdings ({otherInstruments.length})
                  </p>
                  <p className="tabular text-xs font-semibold text-amber-200">
                    {toGbp(otherTotal)}
                  </p>
                </div>
                <p className="mt-1 text-[10px] text-slate-600">{otherCount} purchases</p>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  tone = "default",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "default" | "amber" | "pos";
}) {
  const color = tone === "amber" ? "text-amber-200" : tone === "pos" ? "text-pos" : "text-white";
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className={`tabular mt-1 text-xl font-semibold ${color}`}>{value}</p>
      {note ? <p className="mt-1 text-[10px] text-slate-600">{note}</p> : null}
    </div>
  );
}
