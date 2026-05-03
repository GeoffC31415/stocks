import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BenchmarkPoint, CashflowPoint, EstimatedTimeseriesPoint } from "../lib/api";
import {
  chartUtcMs,
  formatChartMonthTick,
  formatChartTooltipDay,
  formatChartTooltipMonth,
  formatChartDayTick,
} from "../lib/chartDates";
import { toGbp } from "../lib/formatters";

type TimeseriesPoint = {
  as_of_date: string;
  total_value_gbp: number;
  total_book_cost_gbp: number;
};

type ChartTab = "estimated" | "deployment" | "value";

const TABS: { key: ChartTab; label: string }[] = [
  { key: "estimated", label: "Historical estimate" },
  { key: "deployment", label: "Capital deployment" },
  { key: "value", label: "Snapshot history" },
];

const kFormatter = (v: number) => `£${(v / 1000).toFixed(0)}k`;

function DarkTooltip({
  active,
  payload,
  label,
  formatLabel,
}: {
  active?: boolean;
  payload?: Array<{
    name?: string;
    value?: number;
    color?: string;
    dataKey?: string;
  }>;
  label?: string | number;
  formatLabel?: (label: string | number | undefined) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const headline =
    formatLabel != null ? formatLabel(label) : label != null ? String(label) : "";
  return (
    <div className="rounded-xl border border-white/[0.08] bg-aurora-base/95 px-3 py-2 text-xs shadow-glass backdrop-blur-md">
      <p className="font-semibold text-slate-300">{headline}</p>
      <div className="mt-1.5 space-y-1">
        {payload.map((p) => (
          <div key={p.dataKey} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: p.color }}
            />
            <span className="text-slate-400">{p.name}</span>
            <span className="tabular ml-auto font-semibold text-white">
              {p.value != null ? toGbp(p.value as number) : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartPanel({
  cashflow,
  timeseries,
  estimatedTimeseries,
  benchmarks,
  hasOrders,
}: {
  cashflow: CashflowPoint[];
  timeseries: TimeseriesPoint[];
  estimatedTimeseries: EstimatedTimeseriesPoint[];
  benchmarks: BenchmarkPoint[];
  hasOrders: boolean;
}) {
  const [tab, setTab] = useState<ChartTab>("estimated");

  const mergedEstimated = useMemo(() => {
    const byMonth = new Map(cashflow.map((c) => [c.month, c]));
    const benchmarkByMonth = new Map<string, Record<string, number>>();
    for (const point of benchmarks) {
      const month = point.date.slice(0, 7);
      benchmarkByMonth.set(month, {
        ...(benchmarkByMonth.get(month) ?? {}),
        [`benchmark_${point.symbol.replace(/[^a-z0-9]/gi, "_")}`]: point.rebased_value,
      });
    }
    return estimatedTimeseries.map((e) => ({
      month: e.month,
      estimated_value_gbp: e.estimated_value_gbp,
      cumulative_net_deployed:
        byMonth.get(e.month)?.cumulative_net_deployed ?? null,
      ...(benchmarkByMonth.get(e.month) ?? {}),
      chartTime: chartUtcMs(e.month),
    }));
  }, [benchmarks, cashflow, estimatedTimeseries]);

  const benchmarkKeys = useMemo(
    () =>
      Array.from(new Set(benchmarks.map((point) => point.symbol))).map((symbol) => ({
        symbol,
        key: `benchmark_${symbol.replace(/[^a-z0-9]/gi, "_")}`,
      })),
    [benchmarks],
  );

  const cashflowWithTime = useMemo(
    () =>
      cashflow.map((c) => ({
        ...c,
        chartTime: chartUtcMs(c.month),
      })),
    [cashflow],
  );

  const timeseriesWithTime = useMemo(
    () =>
      timeseries.map((p) => ({
        ...p,
        chartTime: chartUtcMs(p.as_of_date),
      })),
    [timeseries],
  );

  const activeTab: ChartTab = hasOrders ? tab : "value";

  const axisStyle = { fontSize: 10, fill: "#64748b" };

  const xAxisMonthTime = (
    <XAxis
      dataKey="chartTime"
      type="number"
      scale="time"
      domain={["dataMin", "dataMax"]}
      stroke="#64748b"
      tick={{ ...axisStyle, fontSize: 11 }}
      tickFormatter={formatChartMonthTick}
      minTickGap={28}
      tickLine={false}
      axisLine={false}
    />
  );

  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          {activeTab === "estimated" && (
            <>
              <h2 className="text-base font-semibold text-white">
                Portfolio value · historical estimate
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Order-derived quantities × current prices. Gap above the
                deployed line is unrealised gain.
              </p>
            </>
          )}
          {activeTab === "deployment" && (
            <>
              <h2 className="text-base font-semibold text-white">
                Capital deployment
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Cumulative net cash invested, DRIP reinvested, sells over time.
              </p>
            </>
          )}
          {activeTab === "value" && (
            <>
              <h2 className="text-base font-semibold text-white">
                Snapshot history
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Actual values from each imported portfolio snapshot.
              </p>
            </>
          )}
        </div>

        {hasOrders && (
          <div className="relative flex shrink-0 gap-1 rounded-full border border-white/[0.06] bg-aurora-base/60 p-1">
            {TABS.map((t) => {
              const isActive = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={`relative rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                    isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {isActive && (
                    <motion.span
                      layoutId="chart-tab-pill"
                      className="absolute inset-0 -z-10 rounded-full bg-aurora-accent shadow-glow-accent"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <span className="relative">{t.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-4 h-72">
        <ResponsiveContainer width="100%" height="100%">
          {activeTab === "estimated" ? (
            <AreaChart data={mergedEstimated}>
              <defs>
                <linearGradient id="estVal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="estDep" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
              {xAxisMonthTime}
              <YAxis
                stroke="#64748b"
                tick={{ ...axisStyle, fontSize: 11 }}
                tickFormatter={kFormatter}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                content={
                  <DarkTooltip
                    formatLabel={(t) =>
                      typeof t === "number" ? formatChartTooltipMonth(t) : String(t ?? "")
                    }
                  />
                }
                cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
                iconType="circle"
              />
              <Area
                type="monotone"
                dataKey="estimated_value_gbp"
                stroke="#22d3ee"
                strokeWidth={2}
                fill="url(#estVal)"
                name="Est. value (current prices)"
              />
              <Area
                type="monotone"
                dataKey="cumulative_net_deployed"
                stroke="#a78bfa"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                fill="url(#estDep)"
                name="Net cash deployed"
              />
              {benchmarkKeys.map(({ symbol, key }, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={index === 0 ? "#fbbf24" : "#f87171"}
                  strokeWidth={1.25}
                  strokeDasharray="4 3"
                  dot={false}
                  name={`Benchmark ${symbol.toUpperCase()}`}
                />
              ))}
            </AreaChart>
          ) : activeTab === "deployment" ? (
            <AreaChart data={cashflowWithTime}>
              <defs>
                <linearGradient id="depNet" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
              {xAxisMonthTime}
              <YAxis
                stroke="#64748b"
                tick={{ ...axisStyle, fontSize: 11 }}
                tickFormatter={kFormatter}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                content={
                  <DarkTooltip
                    formatLabel={(t) =>
                      typeof t === "number" ? formatChartTooltipMonth(t) : String(t ?? "")
                    }
                  />
                }
                cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
                iconType="circle"
              />
              <Area
                type="monotone"
                dataKey="cumulative_net_deployed"
                stroke="#22d3ee"
                strokeWidth={2}
                fill="url(#depNet)"
                name="Net deployed"
              />
              <Line
                type="monotone"
                dataKey="cumulative_drip"
                stroke="#fbbf24"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                name="DRIP cumulative"
              />
              <Line
                type="monotone"
                dataKey="cumulative_sells"
                stroke="#f87171"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                name="Cumulative sells"
              />
            </AreaChart>
          ) : (
            <AreaChart data={timeseriesWithTime}>
              <defs>
                <linearGradient id="snapVal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="snapBook" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
              <XAxis
                dataKey="chartTime"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                stroke="#64748b"
                tick={{ ...axisStyle, fontSize: 11 }}
                tickFormatter={formatChartDayTick}
                minTickGap={32}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#64748b"
                tick={{ ...axisStyle, fontSize: 11 }}
                tickFormatter={kFormatter}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                content={
                  <DarkTooltip
                    formatLabel={(t) =>
                      typeof t === "number" ? formatChartTooltipDay(t) : String(t ?? "")
                    }
                  />
                }
                cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
                iconType="circle"
              />
              <Area
                type="monotone"
                dataKey="total_value_gbp"
                stroke="#22d3ee"
                strokeWidth={2}
                fill="url(#snapVal)"
                name="Value"
              />
              <Area
                type="monotone"
                dataKey="total_book_cost_gbp"
                stroke="#a78bfa"
                strokeWidth={1.5}
                fill="url(#snapBook)"
                name="Book cost"
              />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
