import { useMemo, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Loader2 } from "lucide-react";
import {
  api,
  type PerformanceBenchmarkPoint,
  type PerformanceDrawdownPoint,
} from "../lib/api";
import { chartUtcMs, formatChartDayTick, formatChartTooltipDay } from "../lib/chartDates";
import { SegmentedControl } from "./SegmentedControl";
import { AnalysisStatus } from "./AnalysisStatus";
import { SectionHeader } from "./SectionHeader";
import { ChartTooltip } from "./ChartTooltip";
import { categoryColor, chartTheme } from "../lib/chartTheme";
import { compactGbp, signedGbp, toGbp } from "../lib/formatters";
import { MetricInfo } from "./MetricInfo";
import { groupTimelineEvents, type TimelineEvent } from "../lib/timelineApi";
import { TimelineMarkerLabel } from "./TimelineMarkerLabel";
import type { MetricTopic } from "../lib/metricGlossary";
import { performanceMetric, type PerformanceMetricKey } from "../lib/analysisState";
import type { MetricReason } from "../lib/api";
import { absoluteGbpDomain, absoluteGbpTicks, benchmarkKey as benchKey, joinPerformanceSeries, performanceIndexDomain, performanceIndexTicks, rebaseRowsToGbp, sparseDateTicks, type PerformanceDisplayRow } from "../lib/performanceChart";

import { PERIODS, useAnalysisScope } from "../state/useAnalysisScope";
const PERIOD_SEGMENTS = PERIODS.map((key) => ({ key, label: key === "ALL" ? "All" : key }));

type Tone = "pos" | "neg" | "muted" | "accent";
const TONE_TEXT: Record<Tone, string> = {
  pos: "text-emerald-300",
  neg: "text-rose-300",
  muted: "text-slate-200",
  accent: "text-cyan-200",
};

const indexFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

function MetricTile({
  label,
  value,
  sub,
  tone = "muted",
  infoKey,
  reasons = [],
  context,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  infoKey: MetricTopic;
  reasons?: MetricReason[];
  context: string;
}) {
  return (
    <div className="group relative border border-white/[0.08] bg-[#0a0c10]/60 px-3 py-2.5">
      <div className="flex items-start justify-between gap-1">
        <p className="tufte-label">
          {label}
        </p>
        <MetricInfo iconOnly label={label} topic={infoKey} context={context} />
      </div>
      <p className={`num tabular mt-1 text-lg font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      {sub ? <p className="num mt-0.5 text-[11px] text-slate-400">{sub}</p> : null}

      {reasons.map((reason) => <p key={reason.code} className="mt-1.5 text-xs text-amber-200">{reason.message}</p>)}
    </div>
  );
}

export function PerformancePanel({ accountName, compact = false, focusWindow, timelineEvents = [], onEventDateSelect }: {
  accountName?: string; compact?: boolean; focusWindow?: { start: string; end: string };
  timelineEvents?: TimelineEvent[]; onEventDateSelect?: (date: string) => void;
}) {
  const { period, setPeriod } = useAnalysisScope();
  // Raw account value is an optional overlay, off by default, so the primary
  // line (flow-adjusted) cannot be mistaken for investment return.
  const [showRaw, setShowRaw] = useState(false);
  // Y axis scale: "index" keeps the historical 100 = window start view;
  // "absolute" re-expresses the same series in GBP.
  const [yScale, setYScale] = useState<"index" | "absolute">("index");
  const [chartWidth, setChartWidth] = useState(320);

  const perfQ = useQuery({
    queryKey: ["performance", accountName, period],
    queryFn: () => api.getPerformance(accountName, period),
  });
  const focusStart = focusWindow ? chartUtcMs(focusWindow.start) : null;
  const focusEnd = focusWindow ? chartUtcMs(focusWindow.end) : null;
  const perf = perfQ.data;
  const flow = perf?.flow_adjusted;
  const chainMetric = perf ? performanceMetric(perf, "total_return_pct") : null;
  const chainAvailable = chainMetric?.status === "available" && chainMetric.value != null && Number.isFinite(chainMetric.value);
  const hasFlow = flow != null && ((flow.contributions_gbp ?? 0) > 0 || (flow.withdrawals_gbp ?? 0) > 0);

  const chartData = useMemo(() => {
    if (!perf) return { rows: [] as PerformanceDisplayRow[], benchSymbols: [] as string[] };
    const benchmarks = chainAvailable ? perf.benchmarks ?? [] : [];
    return {
      rows: joinPerformanceSeries({ flow: chainAvailable ? perf.flow_adjusted_curve : [],
        raw: perf.growth_curve, benchmarks }).filter((row) => row.chartTime != null &&
          (focusStart == null || row.chartTime >= focusStart) && (focusEnd == null || row.chartTime <= focusEnd)),
      benchSymbols: Array.from(new Set(benchmarks.map((b) => b.symbol))),
    };
  }, [perf, chainAvailable, focusStart, focusEnd]);

  // Flow-adjusted drawdown area (negative, filled below 0).
  const drawdownData = useMemo(() => {
    if (!perf || !chainAvailable) return [] as Array<Record<string, number | null>>;
    const rows = (perf.drawdown_curve ?? []).map((p: PerformanceDrawdownPoint) => ({
      chartTime: chartUtcMs(p.date),
      drawdown: p.drawdown_pct,
    }));
    rows.sort((a, b) => (a.chartTime ?? 0) - (b.chartTime ?? 0));
    return rows.filter((row) => row.chartTime != null && (focusStart == null || row.chartTime >= focusStart) && (focusEnd == null || row.chartTime <= focusEnd));
  }, [perf, chainAvailable, focusStart, focusEnd]);

  const eventGroups = groupTimelineEvents(timelineEvents).filter((group) =>
    (focusStart == null || chartUtcMs(group.date) >= focusStart) && (focusEnd == null || chartUtcMs(group.date) <= focusEnd));
  const markerDates = new Set(sparseDateTicks([
    ...eventGroups.map((group) => chartUtcMs(group.date)),
    ...(chartData.rows.length ? [chartData.rows[0].chartTime as number, chartData.rows[chartData.rows.length - 1].chartTime as number] : []),
  ], Math.max(100, (chartWidth - 80) * 1.5)));
  const markers = eventGroups.filter((group) => markerDates.has(chartUtcMs(group.date))).slice(0, 12);

  const ticks = sparseDateTicks(chartData.rows.map((row) => row.chartTime as number), chartWidth - 100);
  const drawdownTicks = sparseDateTicks(drawdownData.map((row) => row.chartTime as number), chartWidth - 100);
  // Absolute GBP view is only possible when the window has a positive start
  // value to anchor the chain-linked index; otherwise stay in index mode.
  const startGbp = perf?.start_value_gbp;
  const absoluteAvailable = startGbp != null && Number.isFinite(startGbp) && startGbp > 0;
  const scale: "index" | "absolute" = yScale === "absolute" && absoluteAvailable ? "absolute" : "index";
  // Keep the stored preference honest when the current scope cannot anchor GBP.
  useEffect(() => { if (!absoluteAvailable) setYScale("index"); }, [absoluteAvailable]);
  // Dashed baseline: the index start at 100, or the window start value in the £ view.
  const referenceY = scale === "absolute" && startGbp != null ? startGbp : 100;

  // In the absolute view the index series is re-expressed in GBP. Benchmark
  // price indices have no GBP equivalent, so they are hidden in that view.
  const displayRows = useMemo<PerformanceDisplayRow[]>(() => {
    if (scale !== "absolute") return chartData.rows;
    return rebaseRowsToGbp(chartData.rows, startGbp, chartData.benchSymbols);
  }, [chartData, scale, startGbp]);

  const activeValues = displayRows.flatMap((row) => [
    row.flowAdjusted, ...(showRaw ? [row.rawValue] : []),
    ...(scale === "index" ? chartData.benchSymbols.map((symbol) => row[benchKey(symbol)]) : []),
  ]);
  const yDomain = scale === "index" ? performanceIndexDomain(activeValues) : absoluteGbpDomain(activeValues);
  const yTicks = scale === "index" ? performanceIndexTicks(activeValues) : absoluteGbpTicks(activeValues);

  const benchmarkReturns = useMemo(() => {
    if (!perf || !chainAvailable) return [] as Array<{ symbol: string; returnPct: number }>;
    const lastBySymbol = new Map<string, number>();
    for (const b of (perf.benchmarks ?? []) as PerformanceBenchmarkPoint[]) {
      lastBySymbol.set(b.symbol, b.value);
    }
    return Array.from(lastBySymbol.entries()).map(([symbol, value]) => ({
      symbol,
      returnPct: value / 100 - 1,
    }));
  }, [perf, chainAvailable]);

  if (perfQ.isLoading) {
    return (
      <div className="glass flex min-h-[200px] items-center justify-center rounded-2xl p-5 text-slate-400">
        <Loader2 size={18} className="mr-2 animate-spin" />
        <span className="text-sm">Crunching performance…</span>
      </div>
    );
  }

  if (perfQ.isError) {
    return (
      <div role="alert" className="glass space-y-3 rounded-2xl p-5 text-sm text-slate-300">
        <p>Unable to load performance. No performance estimates are shown.</p>
        <button type="button" onClick={() => void perfQ.refetch()}
          className="min-h-11 rounded-lg border border-white/20 px-4 focus-visible:outline">
          Retry
        </button>
      </div>
    );
  }

  if (!perf || perf.growth_curve.length === 0) {
    return (
      <div className="glass rounded-2xl p-5 text-sm text-slate-400">
        <p>Not enough snapshot history yet to calculate performance. Import a couple more snapshots to unlock growth and risk metrics.</p>
        {perf && <AnalysisStatus kind="unavailable" title="Performance calculations unavailable."
          reasons={Object.values(perf.metrics ?? {}).flatMap(metric=>metric.reasons)} />}
        {perf?.scope?.warnings.map(warning=><p key={warning}>{warning}</p>)}
      </div>
    );
  }

  const sign = (v: number | null): Tone =>
    v == null ? "muted" : v > 0 ? "pos" : v < 0 ? "neg" : "muted";
  const fmtPct = (v: number | null) => (v == null ? "—" : `${v.toFixed(2)}%`);
  const fmtRatio = (v: number | null) => (v == null ? "—" : v.toFixed(2));

  // Missing flow-adjusted metrics must never be replaced with raw account returns.
  const metric = (key: PerformanceMetricKey) => performanceMetric(perf, key);
  const value = (key: PerformanceMetricKey) => chainAvailable && metric(key).status === "available" ? metric(key).value : null;
  const reasons = (key: PerformanceMetricKey) => !chainAvailable ? Array.from(new Map([...(chainMetric?.reasons ?? []), ...metric(key).reasons].map(reason=>[reason.code+reason.message,reason])).values()) : metric(key).reasons;
  const headlineReturn = value("total_return_pct");
  const headlineAnn = value("annualised_return_pct");
  const headlineVol = value("annualised_volatility_pct");
  const headlineSharpe = value("sharpe_ratio");
  const headlineSortino = value("sortino_ratio");
  const headlineDrawdown = value("max_drawdown_pct");

  const windowLabel =
    perf.period_start && perf.period_end
      ? `${perf.period_start} → ${perf.period_end}`
      : "";

  return (
    <div className={compact ? "min-w-0" : "surface-card p-4"}>
      <SectionHeader title="Performance"
        description={compact ? undefined : <>Growth and risk for {windowLabel || "the selected period"}. Returns and risk ratios are flow-adjusted, using observed snapshots and order-derived flow assumptions.</>}
        actions={<SegmentedControl layoutId="perf-period-pill" size="sm" value={period}
          onChange={(p) => setPeriod(p)} segments={PERIOD_SEGMENTS} />} />

      {focusWindow && <p className="mt-3 text-sm text-cyan-200">Chart zoom: {focusWindow.start} – {focusWindow.end}. All metrics still describe the full selected performance period.</p>}

      {/* Cash-flow strip: the money that moved during the window */}
      {!compact && flow && flow.contributions_gbp != null && flow.withdrawals_gbp != null && flow.net_external_flow_gbp != null && (
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
          <span className="font-semibold uppercase tracking-wide text-slate-400">
            Cash flows
          </span>
          <span className="text-emerald-300">
            {signedGbp(flow.contributions_gbp)} in
          </span>
          <span className="text-rose-300">
            {signedGbp(-flow.withdrawals_gbp)} out
          </span>
          <span className="text-slate-300">
            net {signedGbp(flow.net_external_flow_gbp)}
          </span>
          {hasFlow ? (
            <span className="text-slate-500">
              {perf.total_return_pct != null && flow.total_return_pct != null ? (
                <>
                  raw value growth {fmtPct(perf.total_return_pct)} → flow-adjusted{" "}
                  <span className="text-slate-300">{fmtPct(flow.total_return_pct)}</span>
                </>
              ) : (
                "netted out of the return above"
              )}
            </span>
          ) : null}
        </div>
      )}

      {compact && !chainAvailable && <div className="mt-3"><AnalysisStatus kind="unavailable"
        title="Investment return unavailable" reasons={chainMetric?.reasons.slice(0, 1)} /></div>}
      {!compact && <div className="mt-4 space-y-2">
        {!chainAvailable && <AnalysisStatus kind="unavailable"
          title="Flow-adjusted performance unavailable for this window. Raw account values are not a substitute for investment returns."
          reasons={chainMetric?.reasons} />}
        {perf.scope?.warnings.map((warning) => <p key={warning} className="text-sm text-amber-200">{warning}</p>)}
        {(flow?.notes ?? []).filter((note) => note !== "flow-adjusted").map((note) => <p key={note} className="text-xs text-slate-300">{note}</p>)}
        <p className="text-xs text-slate-400">Covered valuation dates: {windowLabel} · {perf.growth_curve.length} sparse snapshot observations, not daily measurements.</p>
        <p className="text-xs text-amber-200">Carried-forward account valuations may mask changes between snapshots. Trade-derived proxy flows are assumptions, not confirmed deposits or withdrawals; synced external flows are used where available.</p>

        <p className="text-xs text-slate-400">{flow?.method ?? "Chain-linked interval Modified Dietz"}{chainAvailable && <> · {chainMetric.observations} adjusted snapshot observations</>} · {windowLabel}. Risk-free assumption: {perf.risk_free_annual_pct}%.</p>
      </div>}
      {!compact && <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricTile
          infoKey="totalReturn" context={windowLabel}
          label="Snapshot investment return"
          value={fmtPct(headlineReturn)}
          reasons={reasons("total_return_pct")}
          sub={
            flow && perf.total_return_pct != null
              ? `raw ${fmtPct(perf.total_return_pct)}`
              : `£${Math.round(perf.start_value_gbp ?? 0).toLocaleString()} → £${Math.round(perf.end_value_gbp ?? 0).toLocaleString()}`
          }
          tone={sign(headlineReturn)}
        />
        <MetricTile
          infoKey="annualised" context={windowLabel}
          label="Annualised"
          value={fmtPct(headlineAnn)}
          reasons={reasons("annualised_return_pct")}
          sub="CAGR over window"
          tone={sign(headlineAnn)}
        />
        <MetricTile
          infoKey="volatility" context={windowLabel}
          label="Volatility"
          value={fmtPct(headlineVol)}
          reasons={reasons("annualised_volatility_pct")}
          sub="Annualised std. dev."
          tone="muted"
        />
        <MetricTile
          infoKey="sharpe" context={`${windowLabel} · risk-free assumption ${perf.risk_free_annual_pct}%`}
          label="Sharpe"
          value={fmtRatio(headlineSharpe)}
          reasons={reasons("sharpe_ratio")}
          sub={`Risk-free assumption ${perf.risk_free_annual_pct}%`}
          tone={sign(headlineSharpe)}
        />
        <MetricTile
          infoKey="sortino" context={`${windowLabel} · risk-free assumption ${perf.risk_free_annual_pct}%`}
          label="Sortino"
          value={fmtRatio(headlineSortino)}
          reasons={reasons("sortino_ratio")}
          sub="Downside-adjusted"
          tone={sign(headlineSortino)}
        />
        <MetricTile
          infoKey="maxDrawdown" context={windowLabel}
          label="Max drawdown"
          value={fmtPct(headlineDrawdown)}
          reasons={reasons("max_drawdown_pct")}
          sub={
            perf.max_drawdown_raw_pct != null
              ? `flow-adjusted · raw ${fmtPct(perf.max_drawdown_raw_pct)}`
              : "flow-adjusted, peak to trough"
          }
          tone={sign(headlineDrawdown)}
        />
      </div>}

      {!compact && <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-400">
          <input
            type="checkbox"
            checked={showRaw && chainAvailable}
            disabled={!chainAvailable}
            onChange={(e) => setShowRaw(e.target.checked)}
            className="h-3.5 w-3.5 accent-cyan-400"
          />
          Show raw account value (dashed)
        </label>
        {absoluteAvailable && chainAvailable && <SegmentedControl layoutId="perf-y-scale" size="sm" value={scale}
          onChange={setYScale} segments={[
            { key: "index", label: "Index (100 = start)" },
            { key: "absolute", label: "Absolute (£)" },
          ]} />}
      </div>}

      {chainAvailable && <div id="performance-chart" role="region" aria-label="Snapshot performance chart" className="mt-2 h-56 overflow-hidden">
        <ResponsiveContainer width="100%" height="100%" onResize={(width) => setChartWidth(width)}>
          <AreaChart data={displayRows} margin={{ top: onEventDateSelect && markers.length ? 56 : 8, right: 36, bottom: 2, left: 4 }}>
            <defs>
              <linearGradient id="perfVal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.11} />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="chartTime"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              stroke="#64748b"
              tick={{ fontSize: 11, fill: chartTheme.axis }}
              tickFormatter={formatChartDayTick}
              ticks={ticks}
              interval={0}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 11, fill: chartTheme.axis }}
              tickFormatter={(v) => (scale === "index" ? indexFmt.format(Number(v)) : compactGbp(v))}
              domain={yDomain}
              ticks={yTicks}
              tickLine={false}
              axisLine={false}
              width={scale === "index" ? 42 : 58}
            />
            <Tooltip
              content={<ChartTooltip formatLabel={(label) => typeof label === "number" ? formatChartTooltipDay(label) : String(label ?? "")}
                formatValue={(value) => value != null ? (scale === "index" ? indexFmt.format(value) : toGbp(value)) : "—"} />}
              cursor={{ stroke: "rgba(255,255,255,0.2)", strokeDasharray: 2 }}
            />
            <ReferenceLine y={referenceY} stroke="rgba(148,163,184,0.35)" strokeDasharray="2 3" />
            {chainAvailable && <Area
              type="linear"
              dot={false}
              activeDot={{ r: 3, fill: "#38bdf8", stroke: "#0a0c10", strokeWidth: 1.5 }}
              isAnimationActive={false}
              dataKey="flowAdjusted"
              stroke="#38bdf8"
              strokeWidth={1.75}
              fill="url(#perfVal)"
              name={scale === "index" ? "Flow-adjusted (index, 100 = start)" : "Flow-adjusted (£, flows excluded)"}
              connectNulls
            />}
            {showRaw ? (
              <Line
                type="linear"
                dataKey="rawValue"
                isAnimationActive={false}
                stroke="#94a3b8"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={{ r: 2 }}
                connectNulls={false}
                name={scale === "index" ? "Raw account value (index)" : "Raw account value (£)"}
              />
            ) : null}
            {scale === "index" && chartData.benchSymbols.map((symbol) => (
              <Line
                key={symbol}
                type="linear"
                dataKey={benchKey(symbol)}
                isAnimationActive={false}
                stroke={categoryColor("benchmark", symbol)}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls
                name={`${symbol.toUpperCase()} (idx)`}
              />
            ))}
            {onEventDateSelect && markers.map((group, index) => <ReferenceLine key={group.date} x={chartUtcMs(group.date)}
              stroke="#94a3b8" strokeOpacity={0.45} strokeDasharray="2 4" ifOverflow="discard"
              label={<TimelineMarkerLabel date={group.date} count={group.events.length} number={index + 1} width={chartWidth} onSelect={onEventDateSelect} />} />)}
          </AreaChart>
        </ResponsiveContainer>
      </div>}

      {compact && chainAvailable && chainMetric.observations < perf.growth_curve.length &&
        <div className="flex items-center gap-1 text-xs text-amber-200">
          <span>{chainMetric.observations} of {perf.growth_curve.length} snapshots used</span>
          <MetricInfo label="Snapshots used" topic="adjustedObservations" iconOnly brief />
        </div>}
      {drawdownData.length > 0 ? (
        <div className="mt-2 border-t border-white/[0.06] pt-2">
          <div className="mb-0.5 flex items-baseline justify-between">
            <p className="tufte-label">Underwater drawdown</p>
            <span className="num text-[10px] text-slate-500">peak = 0.0%</span>
          </div>
          <div role="region" aria-label="Snapshot drawdown chart" className={compact ? "h-20 overflow-hidden" : "h-28 overflow-hidden"}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={drawdownData} margin={{ top: 6, right: 36, bottom: 6, left: 4 }}>
                <defs>
                  <linearGradient id="drawdownVal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#fb7185" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="#fb7185" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="chartTime"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  hide={compact}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fill: chartTheme.axis }}
                  tickFormatter={formatChartDayTick}
                  ticks={drawdownTicks}
                  interval={0}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 10, fill: chartTheme.axis }}
                  tickFormatter={(v) => `${Number(v).toFixed(1)}%`}
                  tickLine={false}
                  axisLine={false}
                  interval={0}
                  width={42}
                  ticks={[Math.floor(Math.min(-1, ...drawdownData.map((row) => row.drawdown ?? 0)) * 10) / 10, 0]}
                  domain={[Math.floor(Math.min(-1, ...drawdownData.map((row) => row.drawdown ?? 0)) * 10) / 10, 0]}
                />
                <Tooltip content={<ChartTooltip
                  formatLabel={(label) => typeof label === "number" && Number.isFinite(label)
                    ? new Date(label).toISOString().slice(0, 10) : String(label ?? "")}
                  formatValue={(value) => value != null && Number.isFinite(value) ? `${String(value)}%` : "Unavailable"}
                />} />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.3)" strokeDasharray="2 3" />
                <Area
                  type="linear"
                  dataKey="drawdown"
                  dot={false}
                  activeDot={{ r: 2.5, fill: "#fb7185" }}
                  isAnimationActive={false}
                  stroke="#fb7185"
                  strokeWidth={1.25}
                  fill="url(#drawdownVal)"
                  name="Drawdown"
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        {chainAvailable && <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-cyan-400" /> Flow-adjusted ({scale === "index" ? "index, 100 = window start" : "£, flows excluded"})
        </span>}
        {showRaw ? (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-slate-400" /> Raw account value ({scale === "index" ? "index" : "£"}, optional)
          </span>
        ) : null}
        {scale === "index" ? benchmarkReturns.map((b) => (
          <span key={b.symbol} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: categoryColor("benchmark", b.symbol) }} />
            {b.symbol.toUpperCase()} {b.returnPct >= 0 ? "+" : ""}
            {(b.returnPct * 100).toFixed(1)}%
          </span>
        )) : null}
        {scale === "absolute" && benchmarkReturns.length > 0 && (
          <span className="text-slate-600">Benchmarks are price indices, shown only in the index view.</span>
        )}
        {!compact && <span className="text-slate-600">
          Snapshot observations, not a measured daily path. Cash added or withdrawn is netted out. Toggle the dashed raw value to see the unadjusted account curve.
        </span>}
      </div>
    </div>
  );
}
