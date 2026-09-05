import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { usePreferences } from "../state/usePreferences";
import { PerformancePanel } from "../components/PerformancePanel";
import { PortfolioReturnCard } from "../components/PortfolioReturnCard";
import { ChartPanel } from "../components/ChartPanel";
import { AnalysisStatus } from "../components/AnalysisStatus";
import { DrawdownEpisodes } from "../components/DrawdownEpisodes";
import { performanceMetric } from "../lib/analysisState";

export function PerformanceWorkspace() {
  const { accountFilter, dripThreshold } = usePreferences();
  const { period } = useAnalysisScope();
  const [params, setParams] = useSearchParams();
  const account = accountFilter === "all" ? undefined : accountFilter;
  const perfQ = useQuery({ queryKey: ["performance", account, period], queryFn: () => api.getPerformance(account, period) });
  const episode = perfQ.data?.drawdown_episodes?.find((row) => row.id === params.get("episode"));
  const chain = perfQ.data ? performanceMetric(perfQ.data, "total_return_pct") : null;
  const returnsQ = useQuery({ queryKey: ["portfolio-returns", accountFilter, period],
    queryFn: () => api.getPortfolioReturns(account, undefined, undefined, period) });
  const timeseriesQ = useQuery({ queryKey: ["timeseries", accountFilter], queryFn: () => api.getTimeseries(account) });
  const analyticsQ = useQuery({ queryKey: ["order-analytics", dripThreshold, accountFilter], queryFn: () => api.getOrderAnalytics(dripThreshold, account) });
  const cashflowQ = useQuery({ queryKey: ["cashflow", dripThreshold, accountFilter], queryFn: () => api.getCashflowTimeseries(dripThreshold, account) });
  const hasOrders = (analyticsQ.data?.total_orders ?? 0) > 0;
  const estimatedQ = useQuery({ queryKey: ["estimated-timeseries", accountFilter], queryFn: () => api.getEstimatedTimeseries(account), enabled: hasOrders });
  const historyError = timeseriesQ.isError || cashflowQ.isError || estimatedQ.isError || analyticsQ.isError;
  const historyLoading = timeseriesQ.isLoading || cashflowQ.isLoading || analyticsQ.isLoading || (hasOrders && estimatedQ.isLoading);
  return <div className="space-y-5">
    <h1 className="text-2xl font-semibold">Performance workspace</h1>
    {params.has("episode") && <div className="text-sm text-slate-300">
      {episode ? "Showing the selected episode's chart window." : "This episode is not available in the selected scope."}
      <button type="button" className="ml-3 min-h-9 text-cyan-200 underline" onClick={() => { const next = new URLSearchParams(params); next.delete("episode"); setParams(next); }}>Show full chart window</button>
    </div>}
    <PerformancePanel accountName={account} focusWindow={episode ? { start: episode.peak_date, end: episode.end_date } : undefined} />
    {perfQ.data && <DrawdownEpisodes episodes={perfQ.data.drawdown_episodes ?? []} available={chain?.status === "available"} reasons={chain?.reasons} />}
    <div className="max-w-2xl"><PortfolioReturnCard summary={returnsQ.data} loading={returnsQ.isLoading}
      error={returnsQ.isError} onRetry={() => void returnsQ.refetch()} /></div>
    <p className="text-sm text-slate-400">The views below show all recorded account history, independent of the selected performance period.
      Raw snapshots, capital deployment and current-price reconstruction are different quantities, not interchangeable return measures.</p>
    {historyError ? <AnalysisStatus kind="error" title="Unable to load complete history views. No partial reconstruction is shown."
      onRetry={() => { void timeseriesQ.refetch(); void cashflowQ.refetch(); void analyticsQ.refetch(); if (hasOrders) void estimatedQ.refetch(); }} />
      : historyLoading ? <p role="status">Loading history views…</p>
      : <ChartPanel cashflow={cashflowQ.data ?? []} timeseries={timeseriesQ.data ?? []} estimatedTimeseries={estimatedQ.data ?? []} hasOrders={hasOrders} />}
  </div>;
}
