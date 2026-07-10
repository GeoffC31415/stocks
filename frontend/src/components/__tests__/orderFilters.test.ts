import { describe, expect, it } from "vitest";
import type { Order } from "../../lib/api";
import { filterOrders } from "../orderFilters";

const order = (id: number, date: string, side: string, isDrip = false): Order =>
  ({ id, order_date: date, side, is_drip: isDrip, security_name: `Security ${id}` }) as Order;

describe("filterOrders", () => {
  const orders = [
    order(1, "2025-01-10T12:00:00Z", "Buy"),
    order(2, "2025-06-15T12:00:00Z", "Buy", true),
    order(3, "2026-01-05T12:00:00Z", "Sell"),
  ];

  it("filters inclusively by date range", () => {
    expect(
      filterOrders(orders, { kind: "all", name: "", from: "2025-06-15", to: "2026-01-05" }).map(
        (item) => item.id,
      ),
    ).toEqual([2, 3]);
  });

  it("combines type and name filters", () => {
    expect(
      filterOrders(orders, { kind: "drip", name: "security 2", from: "", to: "" }).map(
        (item) => item.id,
      ),
    ).toEqual([2]);
  });
});
