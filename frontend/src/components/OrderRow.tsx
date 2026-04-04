import type { Order } from "../lib/api";
import { toGbp, formatOrderDate } from "../lib/formatters";

export function OrderRow({
  order,
  showName = false,
}: {
  order: Order;
  showName?: boolean;
}) {
  const isBuy = order.side.toLowerCase() === "buy";
  const isSell = order.side.toLowerCase() === "sell";

  const badge = order.is_drip
    ? "bg-amber-900/60 text-amber-300 border-amber-700"
    : isBuy
      ? "bg-emerald-900/60 text-emerald-300 border-emerald-700"
      : isSell
        ? "bg-rose-900/60 text-rose-300 border-rose-700"
        : "bg-slate-800 text-slate-400 border-slate-700";

  const label = order.is_drip ? "DRIP" : order.side;

  return (
    <div className="flex items-center gap-2 rounded-lg bg-slate-900/50 px-3 py-2 text-xs transition-colors hover:bg-slate-800/50">
      <span
        className={`shrink-0 rounded border px-1.5 py-0.5 font-semibold ${badge}`}
      >
        {label}
      </span>
      {showName && (
        <span className="min-w-0 flex-1 truncate text-slate-300">
          {order.security_name}
        </span>
      )}
      {!showName && order.quantity != null && (
        <span className="text-slate-400">{order.quantity} shares</span>
      )}
      <span className="ml-auto shrink-0 font-medium text-white">
        {toGbp(order.cost_proceeds_gbp)}
      </span>
      <span className="shrink-0 text-slate-500">
        {formatOrderDate(order.order_date)}
      </span>
    </div>
  );
}
