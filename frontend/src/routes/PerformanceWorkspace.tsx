import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { usePreferences } from "../state/usePreferences";
import { PerformancePanel } from "../components/PerformancePanel";
import { PortfolioReturnCard } from "../components/PortfolioReturnCard";
import { ChartPanel } from "../components/ChartPanel";
import { AnalysisStatus } from "../components/AnalysisStatus";

export function PerformanceWorkspace() {
  const { accountFilter, dripThreshold } = usePreferences();
  const { period } = useAnalysisScope();
  const account = accountFilter === "all" ? undefined : accountFilter;
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
    <PerformancePanel accountName={account} />
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
