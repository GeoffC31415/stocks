import { describe, expect, it } from "vitest";
import type { Order } from "../../lib/api";
import { calculateDripAnalysis } from "../dripAnalysis";

const drip = (id: number, date: string, amount: number, name = "Income Fund"): Order =>
  ({
    id,
    order_date: `${date}T12:00:00Z`,
    side: "Buy",
    is_drip: true,
    cost_proceeds_gbp: amount,
    security_name: name,
  }) as Order;

const buy = (id: number, date: string, amount: number): Order =>
  ({
    ...drip(id, date, amount),
    is_drip: false,
  }) as Order;

describe("calculateDripAnalysis", () => {
  const orders = [
    drip(1, "2024-06-30", 50),
    drip(2, "2025-03-01", 100),
    drip(3, "2025-09-01", 150),
    drip(4, "2026-06-30", 250, "Another Fund"),
    buy(5, "2026-06-30", 1000),
  ];

  it("separates trailing and prior twelve-month DRIP proxies", () => {
    const result = calculateDripAnalysis(orders, new Date("2026-07-01T00:00:00Z"));
    expect(result.trailing12m).toBe(400);
    expect(result.prior12m).toBe(100);
    expect(result.growthPct).toBeCloseTo(300, 2);
    expect(result.total).toBe(550);
  });

  it("groups the reinvestment proxy by year and instrument", () => {
    const result = calculateDripAnalysis(orders, new Date("2026-07-01T00:00:00Z"));
    expect(result.byYear).toEqual([
      { year: 2024, total: 50, count: 1 },
      { year: 2025, total: 250, count: 2 },
      { year: 2026, total: 250, count: 1 },
    ]);
    expect(result.byInstrument[0]).toEqual({ name: "Income Fund", total: 300, count: 3 });
  });
});
