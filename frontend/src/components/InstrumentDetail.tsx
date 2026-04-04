import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info } from "lucide-react";
import type { InstrumentHistoryPoint, Order } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { OrderRow } from "./OrderRow";

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
      <div className="flex h-48 items-center justify-center text-sm text-slate-500">
        Loading history…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-white">Value history</h3>
        {name && <p className="text-xs text-slate-500">{name}</p>}
      </div>

      <div className="h-48 rounded-lg bg-slate-900/30 p-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="as_of_date" stroke="#94a3b8" tick={{ fontSize: 10 }} />
            <YAxis stroke="#94a3b8" tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => toGbp(v as number)} />
            <Line type="monotone" dataKey="value_gbp" stroke="#22d3ee" name="Value" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="book_cost_gbp" stroke="#a78bfa" name="Book cost" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {hasOrders && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Orders</h3>
          {ordersLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : orders.length === 0 ? (
            <p className="text-xs text-slate-500">No matched orders.</p>
          ) : (
            <div className="max-h-40 space-y-1 overflow-auto">
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
    <div className="flex h-48 flex-col items-center justify-center gap-2 text-center">
      <Info size={24} className="text-slate-600" />
      <p className="text-sm text-slate-500">
        Select a holding to see its history and orders.
      </p>
    </div>
  );
}
