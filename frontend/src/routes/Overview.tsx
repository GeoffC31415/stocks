import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { formatOrderDate, signedGbp, toGbp } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { usePreferences } from "../state/usePreferences";
import { performanceMetric } from "../lib/analysisState";
import { HeroKpi } from "../components/HeroKpi";
import { MetricCard } from "../components/MetricCard";
import { MetricInfo } from "../components/MetricInfo";
import { AttributionSummaryCard } from "../components/AttributionSummaryCard";
import { PerformancePanel } from "../components/PerformancePanel";
import { AnalysisStatus } from "../components/AnalysisStatus";

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
    <h1 className="text-2xl font-semibold">Welcome to your portfolio</h1>
    <p>Import a snapshot to start tracking value and investment performance.</p>
    <Link className="btn-primary" to={link("/data?tab=import")}>Import data</Link>
  </section>;

  const metric = perfQ.data ? performanceMetric(perfQ.data, "total_return_pct") : null;
  const returnValue = metric?.value;
  const flow = perfQ.data?.flow_adjusted?.net_external_flow_gbp;
  const windowLabel = perfQ.data?.period_start && perfQ.data.period_end
    ? `${formatOrderDate(perfQ.data.period_start)} – ${formatOrderDate(perfQ.data.period_end)}` : "Selected performance window";
  const unavailable = perfQ.isLoading ? "Loading…" : "Unavailable";
  const dates = summary.scope?.valuation_dates.map((row) => row.date).sort() ?? [];
  const dateLabel = dates.length > 1 && dates[0] !== dates[dates.length - 1]
    ? `${formatOrderDate(dates[0])} – ${formatOrderDate(dates[dates.length - 1])}` : formatOrderDate(summary.as_of_date);

  return <div className="space-y-5" data-testid="portfolio-briefing">
    <header className="flex flex-wrap items-baseline justify-between gap-2">
      <h1 className="text-2xl font-semibold tracking-tight text-white">Portfolio overview</h1>
      <p className="text-xs text-slate-400">{account ?? "All accounts"} · Snapshots {dateLabel}</p>
    </header>
    {summary.scope?.warnings.map((warning) => <p key={warning} className="text-sm text-amber-200">{warning}</p>)}
    <div className="grid gap-3 md:grid-cols-3">
      <HeroKpi label="Portfolio value" value={summary.total_value_gbp} caption="Latest account snapshots · includes cash" />
      <MetricCard label="Snapshot investment return" value={returnValue != null ? `${returnValue.toFixed(2)}%` : unavailable}
        tone={returnValue == null ? "neutral" : returnValue >= 0 ? "positive" : "negative"}
        description={windowLabel} action={<MetricInfo iconOnly label="Snapshot investment return" topic="totalReturn" context={windowLabel} />} />
      <MetricCard label="Net external flows" value={flow != null ? signedGbp(flow) : unavailable}
        description="Observed contributions less withdrawals in the performance window; not investment gain." />
    </div>
    <p className="text-xs text-slate-400 md:hidden">What changed below compares the latest snapshots; it has its own dates, separate from performance.</p>
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-3">
        <PerformancePanel accountName={account} compact />
        <Link className="inline-flex min-h-10 items-center text-sm text-cyan-200 underline" to={link("/portfolio?tab=performance")}>Full performance analysis</Link>
      </div>
      <div className="min-w-0">
        {attributionQ.isError ? <AnalysisStatus kind="error" title="Unable to load snapshot attribution." onRetry={() => void attributionQ.refetch()} />
          : attributionQ.isLoading ? <p role="status">Loading snapshot changes…</p>
          : <AttributionSummaryCard attribution={attributionQ.data ?? null} search={location.search} />}
      </div>
    </div>
    <section className="surface-card p-4 sm:p-5" aria-labelledby="allocation-brief-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="allocation-brief-title" className="text-base font-semibold">Allocation summary</h2>
        <Link className="text-sm text-cyan-200 underline" to={link("/portfolio?tab=allocation")}>Full allocation</Link>
      </div>
      <p className="mt-1 text-xs text-slate-400">Current positions · cash-excluded weights. Cash held separately: {toGbp(summary.cash_value_gbp ?? null)}.</p>
      <ol className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {summary.allocation.slice(0, 6).map((row, index) => <li key={`${row.label}-${index}`} className="min-w-0">
          <div className="flex justify-between gap-3 text-sm"><span className="min-w-0 truncate">{row.label}</span><span className="tabular text-slate-300">{row.weight_pct.toFixed(1)}%</span></div>
          <div className="mt-1 h-1 rounded bg-white/5"><div className="h-1 rounded bg-cyan-300/60" style={{ width: `${Math.min(100, Math.max(0, row.weight_pct))}%` }} /></div>
        </li>)}
      </ol>
    </section>
    <nav aria-label="Explore portfolio" className="flex flex-wrap gap-x-6 gap-y-3 text-sm text-cyan-200">
      <Link className="underline" to={link("/portfolio?tab=holdings")}>Explore holdings</Link>
      <Link className="underline" to={link("/portfolio?tab=returns")}>Lifetime holding returns</Link>
      <Link className="underline" to={link("/activity?tab=changes")}>Snapshot changes</Link>
    </nav>
  </div>;
}
