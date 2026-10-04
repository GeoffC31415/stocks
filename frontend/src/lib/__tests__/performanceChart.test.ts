// @vitest-environment node
import { describe, expect, it } from "vitest";
import { absoluteGbpDomain, absoluteGbpTicks, indexToGbp, joinPerformanceSeries, performanceIndexDomain, performanceIndexTicks, rebaseRowsToGbp, sparseDateTicks } from "../performanceChart";
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
      rawValue: 100, rawGbp: 100, "benchmark:A.B": 101 });
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
  it("anchors clean dynamic performance ticks at 100", () => {
    expect(performanceIndexTicks([98.6, 106.6, 114.6])).toEqual([100, 110, 120]);
    expect(performanceIndexTicks([70, 100, 135])).toContain(100);
  });
  it("keeps baseline 100 and extrema in the index domain", () => {
    const [min, max] = performanceIndexDomain([0, 90, 104, 1000]);
    expect(min).toBeLessThanOrEqual(0);
    expect(max).toBeGreaterThanOrEqual(1000);
    const flat = performanceIndexDomain([100, 100]);
    expect(flat[0]).toBeLessThan(100);
    expect(flat[1]).toBeGreaterThan(100);
  });
  it("re-expresses the joined series in absolute GBP for the £ view", () => {
    const joined = joinPerformanceSeries({
      flow: [{ date: "2026-01-01", index: 100 }, { date: "2026-02-01", index: 110 }],
      raw: [
        { as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 2000 },
        { as_of_date: "2026-02-01", normalized_value: 105, value_gbp: 2100 },
      ],
      benchmarks: [{ date: "2026-01-01", symbol: "FTSE 100", value: 101 }, { date: "2026-02-01", symbol: "FTSE 100", value: 102 }],
    });
    const rebased = rebaseRowsToGbp(joined, 2000, ["FTSE 100"]);
    // The first point lands exactly on the window start value (index 100).
    expect(rebased[0].flowAdjusted).toBe(2000);
    // A 10% index gain scales the start value by 10%.
    expect(rebased[1].flowAdjusted).toBe(2200);
    // The raw overlay switches to the real snapshot GBP values.
    expect(rebased.map((row) => row.rawValue)).toEqual([2000, 2100]);
    // Price indices have no GBP equivalent and are nulled out.
    expect(rebased.map((row) => row["benchmark:FTSE 100"])).toEqual([null, null]);
    // Timestamps survive the rebase.
    expect(rebased.map((row) => row.chartTime)).toEqual(joined.map((row) => row.chartTime));
  });
  it("returns rows unchanged when there is no usable GBP anchor", () => {
    const joined = joinPerformanceSeries({
      flow: [{ date: "2026-01-01", index: 100 }],
      raw: [{ as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 2000 }],
      benchmarks: [],
    });
    for (const start of [0, -5, null, Number.NaN]) {
      expect(rebaseRowsToGbp(joined, start, [])).toBe(joined);
    }
  });
  it("converts a chain-linked index to GBP using the window start value", () => {
    expect(indexToGbp(100, 1000)).toBe(1000);
    expect(indexToGbp(112.5, 800)).toBe(900);
    expect(indexToGbp(110, 1000.5)).toBe(1100.55);
    expect(indexToGbp(null, 1000)).toBeNull();
    expect(indexToGbp(110, null)).toBeNull();
    expect(indexToGbp(110, 0)).toBeNull();
    expect(indexToGbp(110, Number.NaN)).toBeNull();
  });
  it("pads absolute GBP domains and pads flat series by a fraction of the value", () => {
    const [low, high] = absoluteGbpDomain([98, 104, 1000]);
    expect(low).toBeLessThan(98);
    expect(high).toBeGreaterThan(1000);
    const [flatLow, flatHigh] = absoluteGbpDomain([100000, 100000]);
    expect(flatLow).toBeLessThan(100000);
    expect(flatHigh).toBeGreaterThan(100000);
    expect(absoluteGbpDomain([])).toEqual([0, 1]);
  });
  it("emits clean 1-2-5 GBP ticks with no 100 anchor", () => {
    expect(absoluteGbpTicks([98, 104, 1000]).every((t) => Number.isFinite(t))).toBe(true);
    const small = absoluteGbpTicks([1000, 2500]);
    expect(small.length).toBeGreaterThanOrEqual(2);
    const step = small[1] - small[0];
    const magnitude = 10 ** Math.floor(Math.log10(step));
    expect([1, 2, 5, 10].includes(step / magnitude)).toBe(true);
    expect(small[0]).toBeGreaterThanOrEqual(1000);
    expect(absoluteGbpTicks([])).toEqual([]);
  });
});
