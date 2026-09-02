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
  type PerformanceFlowAdjustedPoint,
} from "../lib/api";
import { chartUtcMs, formatChartDayTick, formatChartTooltipDay } from "../lib/chartDates";
import { SegmentedControl } from "./SegmentedControl";

type Period = "1M" | "3M" | "6M" | "1Y" | "YTD" | "ALL";
const PERIODS: { key: Period; label: string }[] = [
  { key: "1M", label: "1M" },
  { key: "3M", label: "3M" },
  { key: "6M", label: "6M" },
  { key: "1Y", label: "1Y" },
  { key: "YTD", label: "YTD" },
  { key: "ALL", label: "All" },
];

const benchKey = (symbol: string) => `bench_${symbol.replace(/[^a-z0-9]/gi, "_")}`;

/** Tooltip copy for each metric: what it is + what typical values look like. */
const METRIC_INFO: Record<string, { definition: string; typical: string }> = {
  totalReturn: {
    definition:
      "Flow-adjusted return (Modified Dietz) over the window. It removes the effect of cash you added or withdrew, so it measures how the money already in the account performed — not how much you put in.",
    typical:
      "A diversified stock portfolio averages roughly +7–12%/yr over the long run. Much higher or lower in any single window; a big positive number that mostly reflects a cash injection is a red flag.",
  },
  annualised: {
    definition:
      "The flow-adjusted return compounded to a per-year rate (CAGR). Useful for comparing returns over different window lengths on the same footing.",
    typical: "≈ the long-run market average of ~7–12%/yr for equities. Only shown for windows of 365 days or more (it is unreliable on short windows).",
  },
  volatility: {
    definition:
      "Annualised volatility (standard deviation of period returns). Higher means bigger swings — both up and down. Flow-adjusted so cash in/out don't inflate it.",
    typical: "≈15–25%/yr for a diversified equity portfolio; ~5–10%/yr for a bond-heavy one; near 0 for cash. Above ~30% is unusually jumpy for a diversified book.",
  },
  sharpe: {
    definition:
      "Return earned per unit of total risk (excess return ÷ volatility), flow-adjusted. A higher Sharpe means you got more return for the risk taken.",
    typical: "≈1 is good, 0.5–1 is solid, below 0.5 is weak, and a negative value means it underperformed the (zero) risk-free rate for the risk taken.",
  },
  sortino: {
    definition:
      "Like the Sharpe, but it only punishes downside risk (how bad the bad periods were), ignoring the upside. Flow-adjusted.",
    typical: "Usually higher than the Sharpe for a portfolio that has few, mild drawdowns. >1 is strong. It can be undefined if there were no losing periods.",
  },
  maxDrawdown: {
    definition:
      "The largest peak-to-trough decline in the flow-adjusted wealth index over the window. It measures how deep a bad stretch got on a cash-flow-neutral basis, so contributions don't flatten it. A small value means a smooth ride.",
    typical: "≈-10% to -20% in mild corrections; equities can see -30% to -50% in a full bear market (e.g. 2008, 2022). The raw-value drawdown is shown alongside it for reference.",
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
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  infoKey: string;
}) {
  const info = METRIC_INFO[infoKey];
  return (
    <div className="group relative rounded-xl bg-white/[0.02] p-3">
      <div className="flex items-center gap-1">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
          {label}
        </p>
        <Info size={12} className="text-slate-500 opacity-60 transition group-hover:opacity-100" />
      </div>
      <p className={`mt-1 tabular text-lg font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p> : null}

      {/* Tooltip: definition + typical values */}
      <div className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 w-64 -translate-x-1/2 rounded-xl border border-white/10 bg-aurora-base/95 p-3 text-left opacity-0 shadow-glass backdrop-blur-md transition duration-150 group-hover:opacity-100">
        <p className="text-xs font-semibold text-white">
          {info.definition}
        </p>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-300">
          <span className="font-semibold text-slate-200">Typical: </span>
          {info.typical}
        </p>
      </div>
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

  const perfQ = useQuery({
    queryKey: ["performance", accountName, period],
    queryFn: () => api.getPerformance(accountName, period),
  });
  const perf = perfQ.data;
  const flow = perf?.flow_adjusted;
  const hasFlow = flow != null && (flow.contributions_gbp > 0 || flow.withdrawals_gbp > 0);

  const chartData = useMemo(() => {
    if (!perf) return { rows: [] as Array<Record<string, number | null>>, benchSymbols: [] as string[] };
    const rows: Array<Record<string, number | null>> = [];
    // Primary line: the chain-linked flow-adjusted wealth index.
    const flowRows: PerformanceFlowAdjustedPoint[] = perf.flow_adjusted_curve ?? [];
    for (const p of flowRows) {
      rows.push({ chartTime: chartUtcMs(p.date), flowAdjusted: p.index });
    }
    // Raw value index, only surfaced when the overlay is toggled on.
    for (const p of perf.growth_curve) {
      if (p.normalized_value == null) continue;
      rows.push({ chartTime: chartUtcMs(p.as_of_date), rawValue: p.normalized_value });
    }
    const benchSymbols = Array.from(new Set((perf.benchmarks ?? []).map((b) => b.symbol)));
    for (const b of perf.benchmarks ?? []) {
      rows.push({ chartTime: chartUtcMs(b.date), [benchKey(b.symbol)]: b.value });
    }
    rows.sort((a, b) => (a.chartTime ?? 0) - (b.chartTime ?? 0));
    return { rows, benchSymbols };
  }, [perf]);

  // Flow-adjusted drawdown area (negative, filled below 0).
  const drawdownData = useMemo(() => {
    if (!perf) return [] as Array<Record<string, number | null>>;
    const rows = (perf.drawdown_curve ?? []).map((p: PerformanceDrawdownPoint) => ({
      chartTime: chartUtcMs(p.date),
      drawdown: p.drawdown_pct,
    }));
    rows.sort((a, b) => (a.chartTime ?? 0) - (b.chartTime ?? 0));
    return rows;
  }, [perf]);

  const benchmarkReturns = useMemo(() => {
    if (!perf) return [] as Array<{ symbol: string; returnPct: number }>;
    const lastBySymbol = new Map<string, number>();
    for (const b of (perf.benchmarks ?? []) as PerformanceBenchmarkPoint[]) {
      lastBySymbol.set(b.symbol, b.value);
    }
    return Array.from(lastBySymbol.entries()).map(([symbol, value]) => ({
      symbol,
      returnPct: value / 100 - 1,
    }));
  }, [perf]);

  if (perfQ.isLoading) {
    return (
      <div className="glass flex min-h-[200px] items-center justify-center rounded-2xl p-5 text-slate-400">
        <Loader2 size={18} className="mr-2 animate-spin" />
        <span className="text-sm">Crunching performance…</span>
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

  // Headline uses flow-adjusted (Dietz) when available; falls back to raw.
  const headlineReturn = flow?.total_return_pct ?? perf.total_return_pct;
  const headlineAnn = flow?.annualised_return_pct ?? perf.annualised_return_pct;
  const headlineVol = flow?.annualised_volatility_pct ?? perf.annualised_volatility_pct;
  const headlineSharpe = flow?.sharpe_ratio ?? perf.sharpe_ratio;
  const headlineSortino = flow?.sortino_ratio ?? perf.sortino_ratio;

  const windowLabel =
    perf.period_start && perf.period_end
      ? `${perf.period_start} → ${perf.period_end}`
      : "";

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Performance</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            Growth and risk for {windowLabel || "the selected period"}. Returns and
            risk ratios are <span className="text-slate-300">flow-adjusted</span> —
            cash you added or withdrew is netted out so growth reflects the market,
            not your contributions.
          </p>
        </div>
        <SegmentedControl
          layoutId="perf-period-pill"
          size="sm"
          value={period}
          onChange={(p) => setPeriod(p)}
          segments={PERIODS}
        />
      </div>

      {/* Cash-flow strip: the money that moved during the window */}
      {flow && (
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

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricTile
          infoKey="totalReturn"
          label="Total return"
          value={fmtPct(headlineReturn)}
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
          sub="CAGR over window"
          tone={sign(headlineAnn)}
        />
        <MetricTile
          infoKey="volatility"
          label="Volatility"
          value={fmtPct(headlineVol)}
          sub="Annualised std. dev."
          tone="muted"
        />
        <MetricTile
          infoKey="sharpe"
          label="Sharpe"
          value={fmtRatio(headlineSharpe)}
          sub="Risk-free 0%"
          tone={sign(headlineSharpe)}
        />
        <MetricTile
          infoKey="sortino"
          label="Sortino"
          value={fmtRatio(headlineSortino)}
          sub="Downside-adjusted"
          tone={sign(headlineSortino)}
        />
        <MetricTile
          infoKey="maxDrawdown"
          label="Max drawdown"
          value={fmtPct(perf.max_drawdown_pct)}
          sub={
            perf.max_drawdown_raw_pct != null
              ? `flow-adjusted · raw ${fmtPct(perf.max_drawdown_raw_pct)}`
              : "flow-adjusted, peak to trough"
          }
          tone={perf.max_drawdown_pct == null ? "muted" : perf.max_drawdown_pct < 0 ? "neg" : "muted"}
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

      <div className="mt-2 h-64">
        <ResponsiveContainer width="100%" height="100%">
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
              minTickGap={32}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={(v) => indexFmt.format(Number(v))}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <Tooltip
              content={<PerformanceTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
            />
            <Area
              type="monotone"
              dataKey="flowAdjusted"
              stroke="#22d3ee"
              strokeWidth={2.5}
              fill="url(#perfVal)"
              name="Flow-adjusted (index, 100 = start)"
              connectNulls
            />
            {showRaw ? (
              <Line
                type="monotone"
                dataKey="rawValue"
                stroke="#94a3b8"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls
                name="Raw account value (index)"
              />
            ) : null}
            {chartData.benchSymbols.map((symbol, index) => (
              <Line
                key={symbol}
                type="monotone"
                dataKey={benchKey(symbol)}
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
      </div>

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
                  minTickGap={32}
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
                  reversed
                />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" strokeDasharray="3 3" />
                <Area
                  type="monotone"
                  dataKey="drawdown"
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
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-cyan-400" /> Flow-adjusted (index, 100 = window start)
        </span>
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
