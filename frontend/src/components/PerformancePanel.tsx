import { useMemo, useState } from "react";
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
import { Info, Loader2 } from "lucide-react";
import {
  api,
  type PerformanceBenchmarkPoint,
  type PerformanceDrawdownPoint,
} from "../lib/api";
import { chartUtcMs, formatChartDayTick, formatChartTooltipDay } from "../lib/chartDates";
import { SegmentedControl } from "./SegmentedControl";
import { AnalysisStatus } from "./AnalysisStatus";
import { SectionHeader } from "./SectionHeader";
import { performanceMetric, type PerformanceMetricKey } from "../lib/analysisState";
import type { MetricReason } from "../lib/api";
import { benchmarkKey as benchKey, joinPerformanceSeries, performanceIndexDomain, sparseDateTicks } from "../lib/performanceChart";

type Period = "1M" | "3M" | "6M" | "1Y" | "YTD" | "ALL";
const PERIODS: { key: Period; label: string }[] = [
  { key: "1M", label: "1M" },
  { key: "3M", label: "3M" },
  { key: "6M", label: "6M" },
  { key: "1Y", label: "1Y" },
  { key: "YTD", label: "YTD" },
  { key: "ALL", label: "All" },
];

/** Method explanations, not generic ratings or investment recommendations. */
const METRIC_INFO: Record<string, { definition: string; limitations: string }> = {
  totalReturn: {
    definition:
      "Chain-linked interval Modified Dietz return over the window. It removes the effect of cash you added or withdrew, so it measures how the money already in the account performed — not how much you put in.",
    limitations: "Snapshot observations are irregular. Order-derived external-flow assumptions can affect this estimate.",
  },
  annualised: {
    definition:
      "The flow-adjusted return compounded to a per-year rate (CAGR). Useful for comparing returns over different window lengths on the same footing.",
    limitations: "Only reported for windows of at least 365 days; it is not a forecast.",
  },
  volatility: {
    definition:
      "Annualised volatility (standard deviation of period returns). Higher means bigger swings — both up and down. Flow-adjusted so cash in/out don't inflate it.",
    limitations: "Annualisation uses the mean snapshot interval. Sparse snapshots do not measure daily market risk.",
  },
  sharpe: {
    definition:
      "Return earned per unit of total risk (excess return ÷ volatility), flow-adjusted. A higher Sharpe means you got more return for the risk taken.",
    limitations: "The default risk-free rate is assumed to be zero, not a measured savings rate. No automatic good/weak rating applies.",
  },
  sortino: {
    definition:
      "Like the Sharpe, but it only punishes downside risk (how bad the bad periods were), ignoring the upside. Flow-adjusted.",
    limitations: "Undefined when downside deviation is zero. Irregular snapshot sampling limits comparisons.",
  },
  maxDrawdown: {
    definition:
      "The largest peak-to-trough decline in the flow-adjusted wealth index over the window. It measures how deep a bad stretch got on a cash-flow-neutral basis, so contributions don't flatten it. Snapshot sampling may miss deeper declines between observations.",
    limitations: "Observed between snapshots; deeper declines between observations may be missed. Raw-value drawdown is a separate measure.",
  },
};

type Tone = "pos" | "neg" | "muted" | "accent";
const TONE_TEXT: Record<Tone, string> = {
  pos: "text-emerald-300",
  neg: "text-rose-300",
  muted: "text-slate-200",
  accent: "text-cyan-200",
};

const indexFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const gbpCompact = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function MetricTile({
  label,
  value,
  sub,
  tone = "muted",
  infoKey,
  reasons = [],
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  infoKey: string;
  reasons?: MetricReason[];
}) {
  const info = METRIC_INFO[infoKey];
  return (
    <div className="group relative rounded-xl bg-white/[0.02] p-3">
      <div className="flex items-center gap-1">
        <p className="text-sm font-medium text-slate-300">
          {label}
        </p>

      </div>
      <p className={`mt-1 tabular text-lg font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-xs text-slate-400">{sub}</p> : null}

      {reasons.map((reason) => <p key={reason.code} className="mt-2 text-xs text-amber-200">{reason.message}</p>)}
      <details className="mt-2 text-xs text-slate-300">
        <summary className="cursor-pointer focus-visible:outline"><Info size={12} className="mr-1 inline" />About {label}</summary>
        <p className="mt-2">{info.definition}</p>
        <p className="mt-2">{info.limitations}</p>
      </details>
    </div>
  );
}

function PerformanceTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string }>;
  label?: number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-xl border border-white/[0.08] bg-aurora-base/95 px-3 py-2 text-xs shadow-glass backdrop-blur-md">
      <p className="font-semibold text-slate-300">
        {typeof label === "number" ? formatChartTooltipDay(label) : ""}
      </p>
      <div className="mt-1.5 space-y-1">
        {payload.map((p) => (
          <div key={p.name} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            <span className="text-slate-400">{p.name}</span>
            <span className="tabular ml-auto font-semibold text-white">
              {p.value != null ? indexFmt.format(p.value) : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PerformancePanel({ accountName }: { accountName?: string }) {
  const [period, setPeriod] = useState<Period>("ALL");
  // Raw account value is an optional overlay, off by default, so the primary
  // line (flow-adjusted) cannot be mistaken for investment return.
  const [showRaw, setShowRaw] = useState(false);
  const [chartWidth, setChartWidth] = useState(320);

  const perfQ = useQuery({
    queryKey: ["performance", accountName, period],
    queryFn: () => api.getPerformance(accountName, period),
  });
  const perf = perfQ.data;
  const flow = perf?.flow_adjusted;
  const chainMetric = perf ? performanceMetric(perf, "total_return_pct") : null;
  const chainAvailable = chainMetric?.status === "available" && chainMetric.value != null && Number.isFinite(chainMetric.value);
  const hasFlow = flow != null && ((flow.contributions_gbp ?? 0) > 0 || (flow.withdrawals_gbp ?? 0) > 0);

  const chartData = useMemo(() => {
    if (!perf) return { rows: [] as Array<Record<string, number | null>>, benchSymbols: [] as string[] };
    const benchmarks = chainAvailable ? perf.benchmarks ?? [] : [];
    return {
      rows: joinPerformanceSeries({ flow: chainAvailable ? perf.flow_adjusted_curve : [],
        raw: perf.growth_curve, benchmarks }),
      benchSymbols: Array.from(new Set(benchmarks.map((b) => b.symbol))),
    };
  }, [perf, chainAvailable]);

  // Flow-adjusted drawdown area (negative, filled below 0).
  const drawdownData = useMemo(() => {
    if (!perf || !chainAvailable) return [] as Array<Record<string, number | null>>;
    const rows = (perf.drawdown_curve ?? []).map((p: PerformanceDrawdownPoint) => ({
      chartTime: chartUtcMs(p.date),
      drawdown: p.drawdown_pct,
    }));
    rows.sort((a, b) => (a.chartTime ?? 0) - (b.chartTime ?? 0));
    return rows;
  }, [perf, chainAvailable]);

  const ticks = sparseDateTicks(chartData.rows.map((row) => row.chartTime as number), chartWidth - 100);
  const drawdownTicks = sparseDateTicks(drawdownData.map((row) => row.chartTime as number), chartWidth - 100);
  const indexDomain = performanceIndexDomain(chartData.rows.flatMap((row) => [
    row.flowAdjusted, ...(showRaw ? [row.rawValue] : []),
    ...chartData.benchSymbols.map((symbol) => row[benchKey(symbol)]),
  ]));

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
        Not enough snapshot history yet to calculate performance. Import a couple
        more snapshots to unlock growth and risk metrics.
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
  const reasons = (key: PerformanceMetricKey) => !chainAvailable ? chainMetric?.reasons ?? [] : metric(key).reasons;
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
    <div className="glass rounded-2xl p-5">
      <SectionHeader title="Performance"
        description={<>Growth and risk for {windowLabel || "the selected period"}. Returns and risk ratios are flow-adjusted, using observed snapshots and order-derived flow assumptions.</>}
        actions={<SegmentedControl layoutId="perf-period-pill" size="sm" value={period}
          onChange={(p) => setPeriod(p)} segments={PERIODS} />} />

      {/* Cash-flow strip: the money that moved during the window */}
      {flow && flow.contributions_gbp != null && flow.withdrawals_gbp != null && flow.net_external_flow_gbp != null && (
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
          <span className="font-semibold uppercase tracking-wide text-slate-400">
            Cash flows
          </span>
          <span className="text-emerald-300">
            +{gbpCompact.format(flow.contributions_gbp)} in
          </span>
          <span className="text-rose-300">
            −{gbpCompact.format(flow.withdrawals_gbp)} out
          </span>
          <span className="text-slate-300">
            net {flow.net_external_flow_gbp >= 0 ? "+" : "−"}
            {gbpCompact.format(Math.abs(flow.net_external_flow_gbp))}
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

      <div className="mt-4 space-y-2">
        {!chainAvailable && <AnalysisStatus kind="unavailable"
          title="Flow-adjusted performance unavailable for this window. Raw account values are not a substitute for investment returns."
          reasons={chainMetric?.reasons} />}
        {perf.scope?.warnings.map((warning) => <p key={warning} className="text-sm text-amber-200">{warning}</p>)}
        {(flow?.notes ?? []).filter((note) => note !== "flow-adjusted").map((note) => <p key={note} className="text-xs text-slate-300">{note}</p>)}
        <p className="text-xs text-slate-400">{flow?.method ?? "Chain-linked interval Modified Dietz"} · {perf.growth_curve.length} snapshot observations · {windowLabel}. Risk-free assumption: {perf.risk_free_annual_pct}%.</p>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricTile
          infoKey="totalReturn"
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
          infoKey="annualised"
          label="Annualised"
          value={fmtPct(headlineAnn)}
          reasons={reasons("annualised_return_pct")}
          sub="CAGR over window"
          tone={sign(headlineAnn)}
        />
        <MetricTile
          infoKey="volatility"
          label="Volatility"
          value={fmtPct(headlineVol)}
          reasons={reasons("annualised_volatility_pct")}
          sub="Annualised std. dev."
          tone="muted"
        />
        <MetricTile
          infoKey="sharpe"
          label="Sharpe"
          value={fmtRatio(headlineSharpe)}
          reasons={reasons("sharpe_ratio")}
          sub={`Risk-free assumption ${perf.risk_free_annual_pct}%`}
          tone={sign(headlineSharpe)}
        />
        <MetricTile
          infoKey="sortino"
          label="Sortino"
          value={fmtRatio(headlineSortino)}
          reasons={reasons("sortino_ratio")}
          sub="Downside-adjusted"
          tone={sign(headlineSortino)}
        />
        <MetricTile
          infoKey="maxDrawdown"
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
      </div>

      <div className="mt-4 flex items-center gap-2">
        <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-400">
          <input
            type="checkbox"
            checked={showRaw}
            onChange={(e) => setShowRaw(e.target.checked)}
            className="h-3.5 w-3.5 accent-cyan-400"
          />
          Show raw account value (dashed)
        </label>
      </div>

      {(chainAvailable || showRaw) && <div role="region" aria-label="Snapshot performance chart" className="mt-2 h-64">
        <ResponsiveContainer width="100%" height="100%" onResize={(width) => setChartWidth(width)}>
          <AreaChart data={chartData.rows}>
            <defs>
              <linearGradient id="perfVal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
            <XAxis
              dataKey="chartTime"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              stroke="#64748b"
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={formatChartDayTick}
              ticks={ticks}
              interval={0}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={(v) => indexFmt.format(Number(v))}
              domain={indexDomain}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <Tooltip
              content={<PerformanceTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
            />
            <ReferenceLine y={100} stroke="#94a3b8" strokeDasharray="3 3" />
            {chainAvailable && <Area
              type="linear"
              dot={{ r: 3 }}
              isAnimationActive={false}
              dataKey="flowAdjusted"
              stroke="#22d3ee"
              strokeWidth={2.5}
              fill="url(#perfVal)"
              name="Flow-adjusted (index, 100 = start)"
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
                name="Raw account value (index)"
              />
            ) : null}
            {chartData.benchSymbols.map((symbol, index) => (
              <Line
                key={symbol}
                type="linear"
                dataKey={benchKey(symbol)}
                isAnimationActive={false}
                stroke={index === 0 ? "#fbbf24" : "#f87171"}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls
                name={`${symbol.toUpperCase()} (idx)`}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>}

      {drawdownData.length > 0 ? (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Flow-adjusted drawdown
          </p>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={drawdownData}>
                <defs>
                  <linearGradient id="drawdownVal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f87171" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#f87171" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="chartTime"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  stroke="#64748b"
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  tickFormatter={formatChartDayTick}
                  ticks={drawdownTicks}
                  interval={0}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  domain={[Math.min(-1, ...drawdownData.map((row) => row.drawdown ?? 0)), 0]}
                />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" strokeDasharray="3 3" />
                <Area
                  type="linear"
                  dataKey="drawdown"
                  dot={{ r: 2 }}
                  isAnimationActive={false}
                  stroke="#f87171"
                  strokeWidth={1.5}
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
          <span className="h-2 w-2 rounded-full bg-cyan-400" /> Flow-adjusted (index, 100 = window start)
        </span>}
        {showRaw ? (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-slate-400" /> Raw account value (index, optional)
          </span>
        ) : null}
        {benchmarkReturns.map((b) => (
          <span key={b.symbol} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            {b.symbol.toUpperCase()} {b.returnPct >= 0 ? "+" : ""}
            {(b.returnPct * 100).toFixed(1)}%
          </span>
        ))}
        <span className="text-slate-600">
          The primary line is flow-adjusted, so cash you added or withdrew is netted out. Toggle
          the dashed raw value to see the unadjusted account curve.
        </span>
      </div>
    </div>
  );
}
