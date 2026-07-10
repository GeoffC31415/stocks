import type { Order } from "../lib/api";

export type OrderFilterKind = "all" | "buy" | "drip" | "sell";

export type OrderFilters = {
  kind: OrderFilterKind;
  name: string;
  from: string;
  to: string;
};

export function filterOrders(orders: Order[], filters: OrderFilters): Order[] {
  const name = filters.name.trim().toLowerCase();
  return orders.filter((order) => {
    const side = order.side.toLowerCase();
    if (filters.kind === "drip" && !order.is_drip) return false;
    if (filters.kind === "buy" && (side !== "buy" || order.is_drip)) return false;
    if (filters.kind === "sell" && side !== "sell") return false;
    if (name && !order.security_name.toLowerCase().includes(name)) return false;

    const day = order.order_date.slice(0, 10);
    if (filters.from && day < filters.from) return false;
    if (filters.to && day > filters.to) return false;
    return true;
  });
}
