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

  const chipClass = order.is_drip
    ? "chip-amber"
    : isBuy
      ? "chip-pos"
      : isSell
        ? "chip-neg"
        : "chip-muted";

  const label = order.is_drip ? "DRIP" : order.side.toUpperCase();

  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-2 text-xs transition-colors hover:border-white/[0.08] hover:bg-white/[0.04]">
      <span className={`chip ${chipClass} shrink-0`}>{label}</span>
      {showName ? (
        <span className="min-w-0 flex-1 truncate text-slate-200">
          {order.security_name}
        </span>
      ) : (
        order.quantity != null && (
          <span className="tabular text-slate-400">
            {order.quantity} shares
          </span>
        )
      )}
      <span className="tabular ml-auto shrink-0 font-semibold text-white">
        {toGbp(order.cost_proceeds_gbp)}
      </span>
      <span className="shrink-0 text-slate-500">
        {formatOrderDate(order.order_date)}
      </span>
    </div>
  );
}
