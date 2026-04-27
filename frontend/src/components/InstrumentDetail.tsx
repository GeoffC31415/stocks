import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info, Loader2 } from "lucide-react";
import type { InstrumentHistoryPoint, Order } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { OrderRow } from "./OrderRow";

function MiniTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; color?: string; name?: string }>;
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-white/[0.08] bg-aurora-base/95 px-2.5 py-1.5 text-[11px] backdrop-blur-md">
      <p className="text-slate-400">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: p.color }}
          />
          <span className="text-slate-500">{p.name}</span>
          <span className="tabular ml-auto text-white">
            {p.value != null ? toGbp(p.value) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function InstrumentDetail({
  name,
  history,
  historyLoading,
  orders,
  ordersLoading,
  hasOrders,
}: {
  name: string | null;
  history: InstrumentHistoryPoint[];
  historyLoading: boolean;
  orders: Order[];
  ordersLoading: boolean;
  hasOrders: boolean;
}) {
  if (historyLoading) {
    return (
      <div className="glass flex h-full min-h-[300px] flex-col items-center justify-center rounded-2xl text-sm text-slate-500">
        <Loader2 size={18} className="animate-spin" />
        <span className="mt-2 text-xs">Loading history…</span>
      </div>
    );
  }

  return (
    <div className="glass flex h-full flex-col gap-4 rounded-2xl p-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Instrument detail
        </p>
        {name && (
          <h3 className="mt-1 truncate text-sm font-semibold text-white" title={name}>
            {name}
          </h3>
        )}
      </div>

      <div className="h-44 rounded-xl bg-white/[0.02] p-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={history}>
            <defs>
              <linearGradient id="instVal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
            <XAxis
              dataKey="as_of_date"
              stroke="#64748b"
              tick={{ fontSize: 10, fill: "#64748b" }}
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
              content={<MiniTooltip />}
              cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
            />
            <Area
              type="monotone"
              dataKey="value_gbp"
              stroke="#22d3ee"
              strokeWidth={2}
              fill="url(#instVal)"
              name="Value"
            />
            <Area
              type="monotone"
              dataKey="book_cost_gbp"
              stroke="#a78bfa"
              strokeWidth={1.25}
              fill="transparent"
              strokeDasharray="3 3"
              name="Book cost"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {hasOrders && (
        <div className="min-h-0 flex-1">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            Orders
          </h3>
          {ordersLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : orders.length === 0 ? (
            <p className="text-xs text-slate-500">No matched orders.</p>
          ) : (
            <div className="max-h-44 space-y-1 overflow-auto pr-1">
              {orders.map((o) => (
                <OrderRow key={o.id} order={o} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function InstrumentDetailEmpty() {
  return (
    <div className="glass flex h-full min-h-[300px] flex-col items-center justify-center gap-2 rounded-2xl p-8 text-center">
      <Info size={22} className="text-slate-600" />
      <p className="text-sm text-slate-400">Select a holding</p>
      <p className="text-xs text-slate-600">
        Click any row to see its history and orders.
      </p>
    </div>
  );
}
