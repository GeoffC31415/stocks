import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Order, OrderAnalytics } from "../lib/api";
import { chartYearStartUtcMs, formatChartYearTick } from "../lib/chartDates";
import { toGbp } from "../lib/formatters";
import { OrderRow } from "./OrderRow";
import { SegmentedControl, type Segment } from "./SegmentedControl";

type OrderFilter = "all" | "buy" | "drip" | "sell";

function filterTone(key: OrderFilter) {
  if (key === "sell") return "neg" as const;
  if (key === "drip") return "amber" as const;
  return "accent" as const;
}

function DripTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number }>;
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const headline =
    typeof label === "number" ? formatChartYearTick(label) : String(label ?? "");
  return (
    <div className="rounded-lg border border-white/[0.08] bg-aurora-base/95 px-2.5 py-1.5 text-[11px] backdrop-blur-md">
      <p className="text-slate-400">{headline}</p>
      <p className="tabular font-semibold text-amber-300">
        {toGbp(payload[0].value as number)}
      </p>
    </div>
  );
}

export function OrderHistorySection({
  orders,
  analytics,
  dripThreshold,
}: {
  orders: Order[];
  analytics: OrderAnalytics;
  dripThreshold: number;
}) {
  const [filter, setFilter] = useState<OrderFilter>("all");

  const counts = useMemo(() => {
    let buy = 0;
    let drip = 0;
    let sell = 0;
    for (const o of orders) {
      if (o.is_drip) drip++;
      else if (o.side.toLowerCase() === "buy") buy++;
      else if (o.side.toLowerCase() === "sell") sell++;
    }
    return { all: orders.length, buy, drip, sell };
  }, [orders]);

  const filtered = useMemo(() => {
    if (filter === "drip") return orders.filter((o) => o.is_drip);
    if (filter === "buy")
      return orders.filter(
        (o) => o.side.toLowerCase() === "buy" && !o.is_drip,
      );
    if (filter === "sell")
      return orders.filter((o) => o.side.toLowerCase() === "sell");
    return orders;
  }, [orders, filter]);

  const segments: Segment<OrderFilter>[] = [
    { key: "all", label: "All", count: counts.all },
    { key: "buy", label: "Buy", count: counts.buy },
    { key: "drip", label: "DRIP", count: counts.drip },
    { key: "sell", label: "Sell", count: counts.sell },
  ];

  const dripByYearChart = useMemo(
    () =>
      analytics.annual_drip.map((row) => ({
        ...row,
        chartTime: chartYearStartUtcMs(row.year),
      })),
    [analytics.annual_drip],
  );

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="glass rounded-2xl p-5 lg:col-span-3">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Order log</h3>
            <p className="text-xs text-slate-500">
              Latest 100 shown · filter to refine.
            </p>
          </div>
          <SegmentedControl
            layoutId="order-filter"
            value={filter}
            onChange={setFilter}
            tone={filterTone(filter)}
            segments={segments}
            size="sm"
          />
        </div>
        <div className="max-h-[480px] space-y-1 overflow-auto pr-1">
          {filtered.slice(0, 100).map((o) => (
            <OrderRow key={o.id} order={o} showName />
          ))}
          {filtered.length === 0 && (
            <p className="py-6 text-center text-sm text-slate-500">
              No orders match this filter.
            </p>
          )}
        </div>
      </div>

      <div className="glass rounded-2xl p-5 lg:col-span-2">
        <h3 className="text-sm font-semibold text-white">DRIP income by year</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          Dividend reinvestments (buys under {toGbp(dripThreshold)}).
        </p>
        <div className="mt-3 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dripByYearChart}>
              <defs>
                <linearGradient id="dripBar" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#fbbf24" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.6} />
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
                tickFormatter={formatChartYearTick}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#64748b"
                tick={{ fontSize: 10, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                content={<DripTooltip />}
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
              />
              <Bar
                dataKey="total_gbp"
                fill="url(#dripBar)"
                name="DRIP (GBP)"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <MiniStat label="Buys" value={String(analytics.buy_count)} />
          <MiniStat
            label="DRIP"
            value={String(analytics.drip_count)}
            tone="amber"
          />
          <MiniStat
            label="Sells"
            value={String(analytics.sell_count)}
            tone="neg"
          />
        </div>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "amber" | "neg";
}) {
  const cls =
    tone === "amber" ? "text-amber-300" : tone === "neg" ? "text-neg" : "text-white";
  return (
    <div className="rounded-xl border border-white/[0.04] bg-white/[0.02] px-3 py-2 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {label}
      </p>
      <p className={`tabular mt-0.5 text-sm font-bold ${cls}`}>{value}</p>
    </div>
  );
}
