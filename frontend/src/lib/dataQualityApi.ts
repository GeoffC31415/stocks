import { requestJson, type AnalysisScope, type MetricReason } from "./api";

export type AttentionItem = {
  id: string; category: "fact" | "rule"; severity: "info" | "warning" | "critical";
  title: string; evidence: string[]; evidence_key: string; action_href: string;
  account_name: string | null; period: string; dismissible: boolean;
};
export type DataConfidence = {
  scope: AnalysisScope; evaluated_on: string; stale_after_days: number;
  snapshots: Array<{ account_name: string; date: string; age_days: number }>;
  transactions: { count: number; first_date: string | null; last_date: string | null;
    unmatched_count: number; review_count: number; completeness: "unknown" };
  classification: Record<string, { holding_count: number; classified_count: number;
    classified_count_pct: number; total_value_gbp: number; classified_value_gbp: number; classified_value_pct: number }>;
  market_history: { covered_value_gbp: number; non_cash_value_gbp: number; covered_pct: number | null;
    aligned_observations: number; cache_gate_met: boolean; validation_pending: boolean; reasons: string[] };
  metric_reasons: MetricReason[]; attention: AttentionItem[];
};
export const dataQualityApi = {
  getConfidence: (account: string | undefined, period: string, staleAfterDays: number) => {
    const params = new URLSearchParams({ period, stale_after_days: String(staleAfterDays) });
    if (account != null) params.set("account_name", account);
    return requestJson<DataConfidence>(`/api/portfolio/data-confidence?${params}`);
  },
};
