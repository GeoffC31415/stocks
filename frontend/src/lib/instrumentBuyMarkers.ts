import type { Order } from "./api";
import { chartUtcMs } from "./chartDates";

function instrumentMarkerDates(orders: Order[], side: "buy" | "sell", excludeDrip: boolean): number[] {
  const dates = new Set<number>();
  for (const order of orders) {
    if (order.side.toLowerCase() !== side || (excludeDrip && order.is_drip)) continue;
    const date = chartUtcMs(order.order_date.slice(0, 10));
    if (Number.isFinite(date)) dates.add(date);
  }
  return [...dates].sort((a, b) => a - b);
}

/** UTC x-coordinates for distinct calendar dates with non-DRIP instrument buys. */
export function instrumentBuyMarkerDates(orders: Order[]): number[] {
  return instrumentMarkerDates(orders, "buy", true);
}

/** UTC x-coordinates for distinct calendar dates with instrument sells. */
export function instrumentSellMarkerDates(orders: Order[]): number[] {
  return instrumentMarkerDates(orders, "sell", false);
}
