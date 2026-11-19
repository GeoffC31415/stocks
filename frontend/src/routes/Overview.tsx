import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { categoryColor } from "../lib/chartTheme";
import { compactGbp, formatOrderDate, signedGbp, toGbp } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { usePreferences } from "../state/usePreferences";
import { performanceMetric } from "../lib/analysisState";
import { MetricInfo } from "../components/MetricInfo";
import { AttributionSummaryCard } from "../components/AttributionSummaryCard";
import { PerformancePanel } from "../components/PerformancePanel";
import { AnalysisStatus } from "../components/AnalysisStatus";
import { DataConfidencePanel } from "../components/DataConfidencePanel";

function KpiCell({
  label,
  value,
  sub,
  tone = "neutral",
  action,
  primary = false,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "positive" | "negative";
  action?: React.ReactNode;
  primary?: boolean;
}) {
  const toneClass =
    tone === "positive"
      ? "text-pos"
      : tone === "negative"
        ? "text-neg"
        : "text-white";
  return (
    <div className="min-w-0 px-3.5 py-2.5">
      <div className="flex items-center justify-between gap-1">
        <span className="tufte-label truncate">{label}</span>
        {action}
      </div>
      <p
        className={`num mt-1 font-semibold leading-none tracking-tight ${
          primary ? "text-2xl sm:text-[26px]" : "text-lg sm:text-xl"
        } ${toneClass}`}
      >
        {value}
      </p>
      {sub && <p className="num mt-1 truncate text-[11px] text-slate-400">{sub}</p>}
    </div>
  );
}

export function Overview() {
  const location = useLocation();
  const { accountFilter } = usePreferences();
  const { period } = useAnalysisScope();
  const account = accountFilter === "all" ? undefined : accountFilter;
  const link = (to: string) => scopedNavigationUrl(to, location.search);
  const summaryQ = useQuery({ queryKey: ["summary", account], queryFn: () => api.getSummary(account) });
  const perfQ = useQuery({ queryKey: ["performance", account, period], queryFn: () => api.getPerformance(account, period) });
  const attributionQ = useQuery({ queryKey: ["snapshot-attribution", accountFilter], queryFn: () => api.getSnapshotAttribution(account) });
  const summary = summaryQ.data;

  if (summaryQ.isLoading) return <p role="status" className="py-12 text-slate-400">Loading portfolio…</p>;
  if (summaryQ.isError) return <AnalysisStatus kind="error" title="Unable to load portfolio summary. No balance is shown."
    onRetry={() => void summaryQ.refetch()} />;
  if (account && summary?.position_count === 0) return <AnalysisStatus kind="empty" title="No holdings for the selected account."
    reasons={[{ code: "empty_account", message: "Choose another account or import a snapshot for this account.", action_href: link("/data?tab=import") }]} />;
  if (!summary || summary.as_of_date == null) return <section className="surface-card mx-auto max-w-xl space-y-4 p-6">
    <h1 className="text-xl font-semibold">Welcome to your portfolio</h1>
    <p>Import a snapshot to start tracking value and investment performance.</p>
    <Link className="btn-primary" to={link("/data?tab=import")}>Import data</Link>
  </section>;

  const perf = perfQ.data;
  const m = (key: "total_return_pct" | "annualised_return_pct" | "annualised_volatility_pct" | "sharpe_ratio" | "sortino_ratio" | "max_drawdown_pct") =>
    perf ? performanceMetric(perf, key) : null;
  const retVal = m("total_return_pct")?.value;
  const cagrVal = m("annualised_return_pct")?.value;
  const volVal = m("annualised_volatility_pct")?.value;
  const sharpeVal = m("sharpe_ratio")?.value;
  const sortinoVal = m("sortino_ratio")?.value;
  const ddVal = m("max_drawdown_pct")?.value;
  const obsCount = m("total_return_pct")?.observations;

  const flow = perf?.flow_adjusted?.net_external_flow_gbp;
  const contrib = perf?.flow_adjusted?.contributions_gbp;
  const withdraw = perf?.flow_adjusted?.withdrawals_gbp;
  const includesNewAccounts = flow != null && perf?.flow_adjusted?.notes?.some((note) =>
    note.startsWith("New accounts enter the all-account series at their first observed value"));
  const windowLabel = perf?.period_start && perf.period_end
    ? `${formatOrderDate(perf.period_start)} – ${formatOrderDate(perf.period_end)}`
    : "Selected window";
  const unavailable = perfQ.isLoading ? "…" : "—";
  const dates = summary.scope?.valuation_dates.map((row) => row.date).sort() ?? [];
  const datesVary = dates.length > 1 && dates[0] !== dates[dates.length - 1];
  const dateLabel = datesVary
    ? `${formatOrderDate(dates[0])} – ${formatOrderDate(dates[dates.length - 1])}`
    : formatOrderDate(summary.as_of_date);

  const cashVal = summary.cash_value_gbp ?? 0;
  const investedVal = summary.invested_value_gbp ?? (summary.total_value_gbp - cashVal);
  const cashPct = summary.total_value_gbp > 0 ? (cashVal / summary.total_value_gbp) * 100 : 0;

  const accountRows = Object.entries(summary.by_account ?? {})
    .map(([name, val]) => ({
      name,
      val,
      pct: summary.total_value_gbp > 0 ? (val / summary.total_value_gbp) * 100 : 0,
    }))
    .sort((a, b) => b.val - a.val);

  const maxAllocPct = Math.max(1, ...summary.allocation.slice(0, 6).map((r) => r.weight_pct));
  const maxAcctPct = Math.max(1, ...accountRows.map((r) => r.pct));

  return (
    <div className="space-y-4" data-testid="portfolio-briefing">
      {/* Compact title line + warnings only when present */}
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <h1 className="text-sm font-semibold tracking-tight text-white">
            Portfolio overview
          </h1>
          <span className="num text-[11px] text-slate-500">
            {account ?? "All accounts"} · {summary.position_count ?? "—"} positions · {windowLabel}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span className="sr-only">{account ?? "All accounts"} · Snapshots {dateLabel}</span>
          {datesVary && (
            <span className="inline-flex items-center gap-1 text-amber-300">
              Dates vary <MetricInfo iconOnly brief label="Snapshot dates" topic="valuationDates" />
            </span>
          )}
          <nav aria-label="Explore portfolio" className="hidden items-center gap-3 sm:flex">
            <Link className="action-link" to={link("/portfolio?tab=holdings")}>Holdings <ArrowUpRight size={11} /></Link>
            <Link className="action-link" to={link("/portfolio?tab=returns")}>Returns <ArrowUpRight size={11} /></Link>
            <Link className="action-link" to={link("/activity?tab=changes")}>Changes <ArrowUpRight size={11} /></Link>
          </nav>
        </div>
      </header>

      {summary.scope?.warnings
        .filter((warning) => !datesVary || !warning.startsWith("Account valuation dates differ"))
        .map((warning) => (
          <p key={warning} className="border-l-2 border-amber-400 bg-amber-400/[0.06] px-3 py-1.5 text-xs text-amber-200">
            {warning}
          </p>
        ))}

      {/* Tufte 6-Metric Hairline KPI Ribbon: maximum data-ink ratio, zero card bloat */}
      <section
        data-testid="overview-metrics"
        aria-label="Key portfolio metrics"
        className="grid grid-cols-2 divide-x divide-y divide-white/[0.08] border-y border-white/[0.1] bg-[#0e1117] sm:grid-cols-3 xl:grid-cols-6 xl:divide-y-0"
      >
        <KpiCell
          primary
          label="Portfolio value"
          value={toGbp(summary.total_value_gbp)}
          sub={`Inv ${compactGbp(investedVal)} · ${cashPct.toFixed(1)}% cash`}
        />
        <KpiCell
          label="Flow-adj return"
          value={retVal != null ? `${retVal >= 0 ? "+" : ""}${retVal.toFixed(2)}%` : unavailable}
          tone={retVal == null ? "neutral" : retVal >= 0 ? "positive" : "negative"}
          sub={
            cagrVal != null
              ? `CAGR +${cagrVal.toFixed(1)}%${perf?.total_return_pct != null ? ` · raw +${perf.total_return_pct.toFixed(1)}%` : ""}`
              : windowLabel
          }
          action={<MetricInfo iconOnly brief label="Snapshot investment return" topic="totalReturn" />}
        />
        <KpiCell
          label="Net flows"
          value={flow != null ? signedGbp(flow) : unavailable}
          sub={
            includesNewAccounts
              ? "Incl. new account entries"
              : contrib != null && withdraw != null
                ? `+${compactGbp(contrib)} in · −${compactGbp(withdraw)} out`
                : windowLabel
          }
          action={
            <MetricInfo
              iconOnly
              brief
              label="Net external flows"
              topic={includesNewAccounts ? "netExternalFlowsWithAccountEntry" : "netExternalFlows"}
              context={windowLabel}
            />
          }
        />
        <KpiCell
          label="Volatility (ann.)"
          value={volVal != null ? `${volVal.toFixed(2)}%` : unavailable}
          sub={obsCount != null ? `${obsCount} snapshot obs` : "Sparse snapshots"}
        />
        <KpiCell
          label="Sharpe / Sortino"
          value={
            sharpeVal != null
              ? `${sharpeVal.toFixed(2)} / ${sortinoVal != null ? sortinoVal.toFixed(2) : "—"}`
              : unavailable
          }
          tone={sharpeVal == null ? "neutral" : sharpeVal >= 0 ? "positive" : "negative"}
          sub={perf?.risk_free_annual_pct != null ? `rf ${perf.risk_free_annual_pct}%` : undefined}
        />
        <KpiCell
          label="Max drawdown"
          value={ddVal != null ? `${ddVal.toFixed(2)}%` : unavailable}
          tone={ddVal != null && ddVal < 0 ? "negative" : "neutral"}
          sub={perf?.max_drawdown_raw_pct != null ? `raw ${perf.max_drawdown_raw_pct.toFixed(2)}%` : "Peak-to-trough"}
        />
      </section>

      {/* Main Tufte Workbench: Left = Small-Multiples Performance+DD + Decomposition Tables; Right = Attribution Bridge & Movers */}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.72fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <div>
            <PerformancePanel accountName={account} compact />
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500">
              <span>Flow-adjusted index (100 = start) aligned with underwater drawdown path.</span>
              <Link className="action-link" to={link("/portfolio?tab=performance")}>
                Full performance analysis <ArrowUpRight size={11} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Hairline Dual Decomposition Strip: Allocation + Accounts side-by-side */}
          <div className="grid gap-6 border-t border-white/[0.09] pt-4 md:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
            <section className="min-w-0" aria-labelledby="allocation-brief-title">
              <div className="flex items-baseline justify-between gap-2 pb-2">
                <div className="flex items-baseline gap-2">
                  <h2 id="allocation-brief-title" className="tufte-label text-slate-200">
                    Allocation (ex-cash)
                  </h2>
                  <span className="num text-[11px] text-slate-500">
                    Cash {toGbp(summary.cash_value_gbp ?? null)}
                  </span>
                </div>
                <Link className="action-link" to={link("/portfolio?tab=allocation")}>
                  Full allocation <ArrowUpRight size={11} aria-hidden="true" />
                </Link>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/[0.09] text-[10px] uppercase tracking-[0.06em] text-slate-500">
                    <th className="py-1 text-left font-medium">Category</th>
                    <th className="w-24 px-2 py-1 text-left font-medium" aria-hidden="true">Dist.</th>
                    <th className="py-1 text-right font-medium">Wt</th>
                    <th className="py-1 pl-3 text-right font-medium">Value</th>
                    <th className="py-1 pl-3 text-right font-medium">Drift</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.allocation.slice(0, 6).map((row, index) => {
                    const color = categoryColor("allocation", row.label);
                    return (
                      <tr key={`${row.label}-${index}`} className="border-b border-white/[0.05] last:border-0">
                        <td className="py-1.5 pr-2">
                          <span className="flex items-center gap-1.5 text-slate-200">
                            <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                            <span className="truncate">{row.label}</span>
                          </span>
                        </td>
                        <td className="px-2 py-1.5" aria-hidden="true">
                          <div className="h-1.5 w-full bg-white/[0.05]">
                            <div
                              className="h-full"
                              style={{ width: `${(row.weight_pct / maxAllocPct) * 100}%`, backgroundColor: color, opacity: 0.85 }}
                            />
                          </div>
                        </td>
                        <td className="num py-1.5 text-right text-slate-200">{row.weight_pct.toFixed(1)}%</td>
                        <td className="num py-1.5 pl-3 text-right text-slate-400">{toGbp(row.value_gbp)}</td>
                        <td className={`num py-1.5 pl-3 text-right ${
                          row.drift_pct == null ? "text-slate-600" : Math.abs(row.drift_pct) >= 1.5 ? "text-amber-300" : "text-slate-500"
                        }`}>
                          {row.drift_pct == null ? "—" : `${row.drift_pct > 0 ? "+" : ""}${row.drift_pct.toFixed(1)}pp`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>

            <section className="min-w-0" aria-label="Account breakdown">
              <div className="flex items-baseline justify-between gap-2 pb-2">
                <h2 className="tufte-label text-slate-200">Accounts</h2>
                <span className="num text-[11px] text-slate-500">{accountRows.length} active</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/[0.09] text-[10px] uppercase tracking-[0.06em] text-slate-500">
                    <th className="py-1 text-left font-medium">Account</th>
                    <th className="w-20 px-2 py-1 text-left font-medium" aria-hidden="true">Share</th>
                    <th className="py-1 text-right font-medium">Wt</th>
                    <th className="py-1 pl-3 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {accountRows.map((acct) => (
                    <tr key={acct.name} className="border-b border-white/[0.05] last:border-0">
                      <td className="py-1.5 pr-2 font-medium text-slate-200">{acct.name}</td>
                      <td className="px-2 py-1.5" aria-hidden="true">
                        <div className="h-1.5 w-full bg-white/[0.05]">
                          <div className="h-full bg-sky-400/75" style={{ width: `${(acct.pct / maxAcctPct) * 100}%` }} />
                        </div>
                      </td>
                      <td className="num py-1.5 text-right text-slate-400">{acct.pct.toFixed(1)}%</td>
                      <td className="num py-1.5 pl-3 text-right text-slate-200">{toGbp(acct.val)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </div>

        {/* Right Analytical Column: Period Attribution Bridge + Movers */}
        <div className="min-w-0 border-t border-white/[0.09] pt-4 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
          {attributionQ.isError ? (
            <AnalysisStatus kind="error" title="Unable to load snapshot attribution." onRetry={() => void attributionQ.refetch()} />
          ) : attributionQ.isLoading ? (
            <p role="status" className="text-xs text-slate-400">Loading snapshot changes…</p>
          ) : (
            <AttributionSummaryCard compact attribution={attributionQ.data ?? null} search={location.search} />
          )}
        </div>
      </div>

      {/* Bottom single-line Data Telemetry Strip */}
      <DataConfidencePanel compact />
    </div>
  );
}
