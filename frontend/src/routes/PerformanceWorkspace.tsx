import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { usePreferences } from "../state/usePreferences";
import { PerformancePanel } from "../components/PerformancePanel";
import { PortfolioReturnCard } from "../components/PortfolioReturnCard";
import { HistoryViews } from "../components/HistoryViews";
import { AnalysisStatus } from "../components/AnalysisStatus";
import { DrawdownEpisodes } from "../components/DrawdownEpisodes";
import { performanceMetric } from "../lib/analysisState";
import { useTimeline } from "../state/useTimeline";
import { TimelineEvents } from "../components/TimelineEvents";
import { parseEventKinds } from "../lib/timelineApi";

export function PerformanceWorkspace() {
  const { accountFilter, dripThreshold } = usePreferences();
  const { period } = useAnalysisScope();
  const [params, setParams] = useSearchParams();
  const account = accountFilter === "all" ? undefined : accountFilter;
  const showEvents = params.get("events") === "on";
  const timelineQ = useTimeline(undefined, showEvents);
  const eventKinds = parseEventKinds(params.get("eventKinds"));
  const perfQ = useQuery({ queryKey: ["performance", account, period], queryFn: () => api.getPerformance(account, period) });
  const episode = perfQ.data?.drawdown_episodes?.find((row) => row.id === params.get("episode"));
  const chain = perfQ.data ? performanceMetric(perfQ.data, "total_return_pct") : null;
  const returnsQ = useQuery({ queryKey: ["portfolio-returns", accountFilter, period],
    queryFn: () => api.getPortfolioReturns(account, undefined, undefined, period) });
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-sm font-semibold tracking-tight text-white">Performance workspace</h1>
      <label className="flex min-h-7 cursor-pointer items-center gap-2 text-xs text-slate-400 hover:text-slate-200"><input type="checkbox" className="h-3.5 w-3.5 accent-sky-400" checked={showEvents}
        onChange={(event) => { const next = new URLSearchParams(params);
          if (event.target.checked) next.set("events", "on"); else { next.delete("events"); next.delete("eventDate"); }
          setParams(next);
        }} />Show timeline events</label>
    </div>
    {params.has("episode") && <div className="text-xs text-slate-300">
      {episode ? "Showing the selected episode's chart window." : "This episode is not available in the selected scope."}
      <button type="button" className="action-link ml-3" onClick={() => { const next = new URLSearchParams(params); next.delete("episode"); setParams(next); }}>Show full chart window</button>
    </div>}
    <PerformancePanel accountName={account} focusWindow={episode ? { start: episode.peak_date, end: episode.end_date } : undefined}
      timelineEvents={showEvents && !timelineQ.isError ? timelineQ.data?.events.filter((event) => eventKinds.includes(event.kind)) : undefined}
      onEventDateSelect={(date) => { const next = new URLSearchParams(params); next.set("eventDate", date); setParams(next); }} />
    {showEvents && <TimelineEvents />}
    {perfQ.data && <DrawdownEpisodes episodes={perfQ.data.drawdown_episodes ?? []} available={chain?.status === "available"} reasons={chain?.reasons} />}
    <div className="max-w-2xl"><PortfolioReturnCard summary={returnsQ.data} loading={returnsQ.isLoading}
      error={returnsQ.isError} onRetry={() => void returnsQ.refetch()} /></div>
    <p className="text-sm text-slate-400">The views below show all recorded account history, independent of the selected performance period.
      Raw snapshots, capital deployment and current-price reconstruction are different quantities, not interchangeable return measures.</p>
    <HistoryViews account={account} dripThreshold={dripThreshold} />
  </div>;
}
