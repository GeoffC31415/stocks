import type { MetricState, PerformanceSummary } from "./api";

export type PerformanceMetricKey = "total_return_pct" | "annualised_return_pct" |
  "annualised_volatility_pct" | "sharpe_ratio" | "sortino_ratio" | "max_drawdown_pct";

/** New metadata wins. Legacy servers still get explicit, conservative reasons. */
export function performanceMetric(perf: PerformanceSummary, key: PerformanceMetricKey): MetricState {
  const metadata = perf.metrics?.[key];
  if (metadata) return metadata;
  const legacyValue = perf.flow_adjusted?.[key] ?? null;
  const value = legacyValue != null && Number.isFinite(legacyValue) ? legacyValue : null;
  const message = key === "annualised_return_pct"
    ? "Annualisation needs at least 365 days and a valid cumulative return."
    : key === "total_return_pct" || key === "max_drawdown_pct"
      ? "A complete, valid flow-adjusted snapshot chain is required."
      : "Risk statistics require enough valid intervals and a defined variance or downside deviation.";
  return {
    status: value != null ? "available" : "unavailable",
    value,
    unit: key.endsWith("ratio") ? "ratio" : "percent",
    method: perf.flow_adjusted?.method ?? "Chain-linked interval Modified Dietz",
    start_date: perf.period_start, end_date: perf.period_end,
    observations: perf.growth_curve.length,
    reasons: value == null ? [{ code: "legacy_unavailable", message, action_href: null }] : [],
  };
}
