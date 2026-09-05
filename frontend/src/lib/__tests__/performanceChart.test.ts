import { describe, expect, it } from "vitest";
import { joinPerformanceSeries, performanceIndexDomain, sparseDateTicks } from "../performanceChart";
import { chartUtcMs } from "../chartDates";

describe("performance presentation geometry", () => {
  it("joins named series at one timestamp without losing valid values", () => {
    const rows = joinPerformanceSeries({
      flow: [{ date: "2026-01-01", index: 100 }, { date: "2026-02-01", index: 110 }],
      raw: [{ as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 100 },
        { as_of_date: "2026-01-01", normalized_value: null, value_gbp: null }],
      benchmarks: [{ date: "2026-01-01", symbol: "A.B", value: 101 }],
    });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ chartTime: chartUtcMs("2026-01-01"), flowAdjusted: 100,
      rawValue: 100, "benchmark:A.B": 101 });
  });
  it("does not conflate punctuation in benchmark identity or invent missing values", () => {
    const rows = joinPerformanceSeries({ flow: [], raw: [], benchmarks: [
      { date: "2026-01-01", symbol: "A.B", value: 101 },
      { date: "2026-01-01", symbol: "A_B", value: 102 },
      { date: "invalid", symbol: "A_B", value: 103 },
    ] });
    expect(rows).toHaveLength(1);
    expect(rows[0]["benchmark:A.B"]).toBe(101);
    expect(rows[0]["benchmark:A_B"]).toBe(102);
    expect(rows[0].flowAdjusted).toBeUndefined();
  });
  it("selects sparse unique ticks by pixel distance, not observation rank", () => {
    const days = [1, 1, 2, 3, 4, 5, 30].map((day) => chartUtcMs(`2026-01-${String(day).padStart(2, "0")}`));
    expect(sparseDateTicks(days, 200)).toEqual([days[0], days[days.length - 1]]);
    const ticks = sparseDateTicks(days, 800);
    expect(new Set(ticks).size).toBe(ticks.length);
    expect(ticks.length).toBeLessThan(days.length - 1);
    expect(sparseDateTicks([], 300)).toEqual([]);
  });
  it("keeps baseline 100 and extrema in the index domain", () => {
    const [min, max] = performanceIndexDomain([0, 90, 104, 1000]);
    expect(min).toBeLessThanOrEqual(0);
    expect(max).toBeGreaterThanOrEqual(1000);
    const flat = performanceIndexDomain([100, 100]);
    expect(flat[0]).toBeLessThan(100);
    expect(flat[1]).toBeGreaterThan(100);
  });
});
