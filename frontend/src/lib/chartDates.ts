/**
 * Recharts categorical axes space points evenly; for portfolio history we map to
 * UTC milliseconds and use scale="time" so pixel distance matches calendar distance.
 */

/** ISO calendar segments: YYYY-MM or YYYY-MM-DD, or full ISO datetime. */
export function chartUtcMs(iso: string): number {
  if (!iso) return NaN;
  const trimmed = iso.trim();
  if (trimmed.includes("T")) {
    const parsed = Date.parse(trimmed);
    return Number.isNaN(parsed) ? NaN : parsed;
  }
  const parts = trimmed.split("-").map((x) => parseInt(x, 10));
  const y = parts[0];
  const mo = parts[1];
  const day = parts[2];
  if (!y || !mo || Number.isNaN(y) || Number.isNaN(mo)) return NaN;
  const d = day != null && !Number.isNaN(day) ? day : 1;
  return Date.UTC(y, mo - 1, d);
}

export function chartYearStartUtcMs(year: number): number {
  return Date.UTC(year, 0, 1);
}

const tickDayFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "2-digit",
});

const tickMonthFmt = new Intl.DateTimeFormat("en-GB", {
  month: "short",
  year: "numeric",
});

const tooltipDayFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

const tooltipMonthFmt = new Intl.DateTimeFormat("en-GB", {
  month: "long",
  year: "numeric",
});

export function formatChartDayTick(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  return tickDayFmt.format(new Date(ms));
}

export function formatChartMonthTick(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  return tickMonthFmt.format(new Date(ms));
}

export function formatChartYearTick(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  return String(new Date(ms).getUTCFullYear());
}

export function formatChartTooltipDay(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  return tooltipDayFmt.format(new Date(ms));
}

export function formatChartTooltipMonth(ms: number): string {
  if (!Number.isFinite(ms)) return "";
  return tooltipMonthFmt.format(new Date(ms));
}
