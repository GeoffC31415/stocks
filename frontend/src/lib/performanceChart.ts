import type { PerformanceBenchmarkPoint, PerformanceFlowAdjustedPoint, PerformancePoint } from "./api";
import { chartUtcMs } from "./chartDates";

export const benchmarkKey = (symbol: string) => `benchmark:${symbol}`;
export type PerformanceDisplayRow = { chartTime: number; [series: string]: number | null };

/** Presentation join only. Canonical financial dates/validity belong to the backend. */
export function joinPerformanceSeries({ flow, raw, benchmarks }: {
  flow: PerformanceFlowAdjustedPoint[];
  raw: PerformancePoint[];
  benchmarks: PerformanceBenchmarkPoint[];
}): PerformanceDisplayRow[] {
  const rows = new Map<number, PerformanceDisplayRow>();
  const put = (date: string, series: string, value: number | null) => {
    const chartTime = chartUtcMs(date);
    if (!Number.isFinite(chartTime)) return;
    const row = rows.get(chartTime) ?? { chartTime };
    // A missing value must not overwrite a valid named observation in a join.
    if (value != null && Number.isFinite(value)) row[series] = value;
    else if (!(series in row)) row[series] = null;
    rows.set(chartTime, row);
  };
  flow.forEach((point) => put(point.date, "flowAdjusted", point.index));
  // Raw snapshots carry both the absolute GBP value and the window-normalized
  // index; the chart picks the axis per mode.
  raw.forEach((point) => {
    put(point.as_of_date, "rawValue", point.normalized_value);
    put(point.as_of_date, "rawGbp", point.value_gbp);
  });
  benchmarks.forEach((point) => put(point.date, benchmarkKey(point.symbol), point.value));
  return [...rows.values()].sort((a, b) => a.chartTime - b.chartTime);
}

/** Reserve label space on a calendar-scaled axis, including both endpoints. */
export function sparseDateTicks(dates: number[], width: number): number[] {
  const unique = [...new Set(dates.filter(Number.isFinite))].sort((a, b) => a - b);
  if (unique.length <= 1) return unique;
  const first = unique[0], last = unique[unique.length - 1];
  const gap = (last - first) * Math.min(1, 100 / Math.max(100, width));
  const ticks = [first];
  for (const date of unique.slice(1, -1)) {
    if (date - ticks[ticks.length - 1] >= gap && last - date >= gap) ticks.push(date);
  }
  return [...ticks, last];
}

export function performanceIndexDomain(values: Array<number | null | undefined>): [number, number] {
  const finite = values.filter((value): value is number => value != null && Number.isFinite(value));
  const low = Math.min(100, ...finite), high = Math.max(100, ...finite);
  const padding = Math.max(1, (high - low) * 0.05);
  return [low - padding, high + padding];
}

export function performanceIndexTicks(values: Array<number | null | undefined>): number[] {
  const finite = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!finite.length) return [100];
  const low = Math.min(100, ...finite), high = Math.max(100, ...finite);
  const rawStep = Math.max(1, (high - low) / 3);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const step = multiplier * magnitude;
  const first = 100 + Math.ceil((low - 100) / step) * step;
  const last = 100 + Math.ceil((high - 100) / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= last + step * 0.001; value += step) ticks.push(Number(value.toFixed(10)));
  if (!ticks.includes(100)) ticks.push(100);
  return [...new Set(ticks)].sort((a, b) => a - b);
}

/** Convert a chain-linked wealth index (100 = window start) to an absolute GBP value. */
export function indexToGbp(index: number | null | undefined, startValueGbp: number | null | undefined): number | null {
  if (index == null || !Number.isFinite(index)) return null;
  if (startValueGbp == null || !Number.isFinite(startValueGbp) || startValueGbp <= 0) return null;
  return Math.round(startValueGbp * index / 100 * 100) / 100;
}

/**
 * Re-express a joined performance row set in absolute GBP for the £ view.
 * The flow-adjusted index (100 = window start) is scaled by the window start
 * value; the raw overlay switches to the real snapshot GBP value; benchmark
 * price indices have no GBP equivalent and are nulled out.
 */
export function rebaseRowsToGbp(rows: PerformanceDisplayRow[], startValueGbp: number | null | undefined, benchSymbols: string[]): PerformanceDisplayRow[] {
  if (startValueGbp == null || !Number.isFinite(startValueGbp) || startValueGbp <= 0) return rows;
  return rows.map((row) => {
    const next: PerformanceDisplayRow = { ...row, flowAdjusted: indexToGbp(row.flowAdjusted, startValueGbp), rawValue: row.rawGbp };
    for (const symbol of benchSymbols) next[benchmarkKey(symbol)] = null;
    return next;
  });
}

/** Domain for absolute GBP values, padded so flat series still get breathing room. */
export function absoluteGbpDomain(values: Array<number | null | undefined>): [number, number] {
  const finite = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!finite.length) return [0, 1];
  const low = Math.min(...finite), high = Math.max(...finite);
  const padding = Math.max(1, (high - low) * 0.05, Math.abs(high) * 0.02);
  return [low - padding, high + padding];
}

/** Clean 1-2-5 step GBP ticks covering an absolute domain (no 100 anchor). */
export function absoluteGbpTicks(values: Array<number | null | undefined>): number[] {
  const finite = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!finite.length) return [];
  const [low, high] = absoluteGbpDomain(values);
  const rawStep = Math.max(1, (high - low) / 4);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const step = multiplier * magnitude;
  const ticks: number[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high + step * 0.001; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks;
}
