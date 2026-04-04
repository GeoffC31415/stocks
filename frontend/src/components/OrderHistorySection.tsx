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
import { toGbp } from "../lib/formatters";
import { OrderRow } from "./OrderRow";

type OrderFilter = "all" | "buy" | "drip" | "sell";

const FILTERS: { key: OrderFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "buy", label: "Buy" },
  { key: "drip", label: "DRIP" },
  { key: "sell", label: "Sell" },
];

function filterColor(key: OrderFilter, active: boolean): string {
  if (!active) return "bg-slate-800/60 text-slate-400 hover:text-slate-200";
  if (key === "sell") return "bg-rose-600 text-white";
  if (key === "drip") return "bg-amber-600 text-white";
  return "bg-cyan-600 text-white";
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

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      {/* Order list */}
      <div className="lg:col-span-3">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">
            Order history
          </h3>
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${filterColor(
                  f.key,
                  filter === f.key,
                )}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-80 space-y-1 overflow-auto rounded-xl border border-slate-700/40 bg-slate-900/20 p-2">
          {filtered.slice(0, 100).map((o) => (
            <OrderRow key={o.id} order={o} showName />
          ))}
          {filtered.length === 0 && (
            <p className="py-4 text-center text-sm text-slate-500">
              No orders match this filter.
            </p>
          )}
        </div>
      </div>

      {/* DRIP by year */}
      <div className="lg:col-span-2">
        <h3 className="mb-1 text-sm font-semibold text-slate-200">
          DRIP income by year
        </h3>
        <p className="mb-3 text-[11px] text-slate-500">
          Dividend reinvestments (buys under {toGbp(dripThreshold)}).
        </p>
        <div className="h-52 rounded-lg bg-slate-900/30 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={analytics.annual_drip}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="year" stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => toGbp(v as number)} />
              <Bar
                dataKey="total_gbp"
                fill="#f59e0b"
                name="DRIP (GBP)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          <MiniStat label="Total buys" value={String(analytics.buy_count)} />
          <MiniStat
            label="DRIP orders"
            value={String(analytics.drip_count)}
            valueClass="text-amber-300"
          />
          <MiniStat
            label="Sell orders"
            value={String(analytics.sell_count)}
            valueClass="text-rose-300"
          />
        </div>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  valueClass = "text-white",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg bg-slate-900/50 px-2 py-2 text-center">
      <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className={`text-sm font-bold ${valueClass}`}>{value}</p>
    </div>
  );
}
