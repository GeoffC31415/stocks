import { describe, expect, it } from "vitest";
import type { Instrument } from "../../lib/api";
import { calculateAllocation } from "../allocationAnalysis";

const holding = (
  id: number,
  value: number,
  assetClass: string | null,
  sector: string | null = null,
): Instrument =>
  ({
    id,
    identifier: `H${id}`,
    security_name: `Holding ${id}`,
    latest_value_gbp: value,
    asset_class: assetClass,
    sector,
    region: null,
    is_cash: false,
    closed_at: null,
  }) as Instrument;

describe("calculateAllocation", () => {
  const instruments = [
    holding(1, 60, "Equity ETF", "Technology"),
    holding(2, 30, "Equity ETF", null),
    holding(3, 10, null, "Industrials"),
  ];

  it("calculates concentration and top holding weights", () => {
    const result = calculateAllocation(instruments, "asset_class");
    expect(result.totalValue).toBe(100);
    expect(result.top1Pct).toBe(60);
    expect(result.top5Pct).toBe(100);
    expect(result.hhi).toBe(4600);
  });

  it("keeps missing classifications visible", () => {
    expect(calculateAllocation(instruments, "asset_class").categories).toEqual([
      { label: "Equity ETF", value: 90, weightPct: 90, count: 2 },
      { label: "Unclassified", value: 10, weightPct: 10, count: 1 },
    ]);
    expect(calculateAllocation(instruments, "sector").categories).toContainEqual({
      label: "Unclassified",
      value: 30,
      weightPct: 30,
      count: 1,
    });
  });
});
