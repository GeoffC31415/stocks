import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2 } from "lucide-react";
import { api, type PerformanceBenchmarkPoint } from "../lib/api";
import {
  chartUtcMs,
  formatChartDayTick,
  formatChartTooltipDay,
} from "../lib/chartDates";
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

type Tone = "pos" | "neg" | "muted" | "accent";
const TONE_TEXT: Record<Tone, string> = {
  pos: "text-emerald-300",
  neg: "text-rose-300",
  muted: "text-slate-300",
  accent: "text-cyan-200",
};

const indexFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

function MetricTile({
  label,
  value,
  sub,
  tone = "muted",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl bg-white/[0.02] p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className={`mt-1 tabular text-lg font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-slate-500">{sub}</p> : null}
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

  const perfQ = useQuery({
    queryKey: ["performance", accountName, period],
    queryFn: () => api.getPerformance(accountName, period),
  });

  const perf = perfQ.data;

  const chartData = useMemo(() => {
    if (!perf) return { rows: [] as Array<Record<string, number | null>>, benchSymbols: [] as string[] };
    const rows: Array<Record<string, number | null>> = [];
    for (const p of perf.growth_curve) {
      if (p.normalized_value == null) continue;
      rows.push({ chartTime: chartUtcMs(p.as_of_date), portfolio: p.normalized_value });
    }
    const benchSymbols = Array.from(new Set((perf.benchmarks ?? []).map((b) => b.symbol)));
    for (const b of perf.benchmarks ?? []) {
      rows.push({ chartTime: chartUtcMs(b.date), [benchKey(b.symbol)]: b.value });
    }
    rows.sort((a, b) => (a.chartTime ?? 0) - (b.chartTime ?? 0));
    return { rows, benchSymbols };
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
  const fmtPct = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "" : ""}${v.toFixed(2)}%`);
  const fmtRatio = (v: number | null) => (v == null ? "—" : v.toFixed(2));

  const windowLabel =
    perf.period_start && perf.period_end
      ? `${perf.period_start} → ${perf.period_end}`
      : "";

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Performance</h2>
          <p className="mt-1 text-xs text-slate-500">
            Growth and risk over {windowLabel || "the selected period"}. Normalised
            to 100 at the start of the window.
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

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricTile
          label="Total return"
          value={fmtPct(perf.total_return_pct)}
          sub={`£${Math.round(perf.start_value_gbp ?? 0).toLocaleString()} → £${Math.round(perf.end_value_gbp ?? 0).toLocaleString()}`}
          tone={sign(perf.total_return_pct)}
        />
        <MetricTile
          label="Annualised"
          value={fmtPct(perf.annualised_return_pct)}
          sub="CAGR over window"
          tone={sign(perf.annualised_return_pct)}
        />
        <MetricTile
          label="Volatility"
          value={fmtPct(perf.annualised_volatility_pct)}
          sub="Annualised std. dev."
          tone="muted"
        />
        <MetricTile
          label="Sharpe"
          value={fmtRatio(perf.sharpe_ratio)}
          sub="Risk-free 0%"
          tone={sign(perf.sharpe_ratio)}
        />
        <MetricTile
          label="Sortino"
          value={fmtRatio(perf.sortino_ratio)}
          sub="Downside-adjusted"
          tone={sign(perf.sortino_ratio)}
        />
        <MetricTile
          label="Max drawdown"
          value={fmtPct(perf.max_drawdown_pct)}
          sub="Peak to trough"
          tone={perf.max_drawdown_pct == null ? "muted" : perf.max_drawdown_pct < 0 ? "neg" : "muted"}
        />
      </div>

      <div className="mt-4 h-64">
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
              dataKey="portfolio"
              stroke="#22d3ee"
              strokeWidth={2.5}
              fill="url(#perfVal)"
              name="Portfolio"
            />
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

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-cyan-400" /> Portfolio (index, 100 = window start)
        </span>
        {benchmarkReturns.map((b) => (
          <span key={b.symbol} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            {b.symbol.toUpperCase()} {b.returnPct >= 0 ? "+" : ""}
            {(b.returnPct * 100).toFixed(1)}%
          </span>
        ))}
        {perf.coverage_start ? (
          <span className="text-slate-600">
            All-account window starts {perf.coverage_start} (first date every account had coverage).
          </span>
        ) : null}
      </div>
    </div>
  );
}
