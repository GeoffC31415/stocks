import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { dataQualityApi } from "../lib/dataQualityApi";
import { formatOrderDate } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { AttentionList } from "./AttentionList";
import { AnalysisStatus } from "./AnalysisStatus";

const TOLERANCES = [7, 14, 30, 60, 90, 365];
const STORAGE = "portfolio.snapshotFreshnessDays.v1";
function storedTolerance() {
  try { const value = Number(localStorage.getItem(STORAGE)); return TOLERANCES.includes(value) ? value : 14; }
  catch { return 14; }
}
const dateLabel = (date: string | null) => date ? formatOrderDate(date) : "Not recorded";

export function DataConfidencePanel({ compact = false }: { compact?: boolean }) {
  const { accountFilter } = usePreferences();
  const { period } = useAnalysisScope();
  const [staleDays, setStaleDays] = useState(storedTolerance);
  const account = accountFilter === "all" ? undefined : accountFilter;
  const query = useQuery({ queryKey: ["data-confidence", account, period, staleDays],
    queryFn: () => dataQualityApi.getConfidence(account, period, staleDays) });
  const data = query.data;
  const critical = data?.attention.filter((item) => item.severity === "critical") ?? [];
  const reminders = data?.attention.filter((item) => item.severity !== "critical") ?? [];
  return <section className="surface-card min-w-0 space-y-3 p-4 [overflow-wrap:anywhere] sm:p-5" aria-label="Data confidence">
    <h2 className="text-base font-semibold">Data confidence</h2>
    {query.isLoading ? <p role="status" className="text-sm text-slate-400">Checking recorded data…</p>
      : query.isError ? <AnalysisStatus kind="error" title="Unable to check data confidence." onRetry={() => void query.refetch()} />
      : data && <>
        {critical.length > 0 && <AttentionList items={critical} />}
        <details open={!compact}>
          <summary className="cursor-pointer text-sm text-slate-300">{data.attention.length === 0
            ? "Core data checks healthy — view coverage and limitations"
            : `${data.attention.length} data check${data.attention.length === 1 ? "" : "s"} need attention — view evidence`}</summary>
          <div className="mt-4 space-y-4">
            <AttentionList items={reminders} />
            <label className="flex flex-wrap items-center gap-2 text-sm text-slate-300">Snapshot freshness tolerance
              <select aria-label="Snapshot freshness tolerance" className="min-h-9 rounded bg-aurora-base px-2" value={staleDays}
                onChange={(event) => { const value = Number(event.target.value); setStaleDays(value);
                  try { localStorage.setItem(STORAGE, String(value)); } catch { /* Optional preference. */ } }}>
                {TOLERANCES.map((days) => <option key={days} value={days}>{days} days</option>)}
              </select>
            </label>
            <div className="space-y-1 text-xs text-slate-400">
              <h3 className="font-semibold text-slate-300">Snapshot freshness</h3>
              {data.snapshots.map((row) => <p key={row.account_name}>{row.account_name}: {dateLabel(row.date)} · {row.age_days} days old</p>)}
              <p>Evaluated {dateLabel(data.evaluated_on)}. Performance still ends at covered valuation dates.</p>
            </div>
            <div className="space-y-1 text-xs text-slate-400">
              <h3 className="font-semibold text-slate-300">Recorded transaction coverage</h3>
              <p>{data.transactions.count} transactions · {dateLabel(data.transactions.first_date)} – {dateLabel(data.transactions.last_date)}</p>
              <p>All recorded transactions for this account scope, independent of performance period. Completeness is unknown; unrecorded dividends and flows cannot be inferred as zero.</p>
            </div>
            <div className="space-y-1 text-xs text-slate-400">
              <h3 className="font-semibold text-slate-300">Classification coverage</h3>
              {Object.entries(data.classification).map(([dimension, coverage]) => <p key={dimension}>{dimension.replace("_", " ")}: {coverage.holding_count
                ? `${coverage.classified_count}/${coverage.holding_count} holdings · ${coverage.classified_value_pct.toFixed(1)}% by positive non-cash value`
                : "No eligible non-cash holdings"}</p>)}
              <p>Product classification is not fund look-through.</p>
            </div>
            {data.metric_reasons.length > 0 && <div className="space-y-1 text-xs text-slate-400"><h3 className="font-semibold text-slate-300">Metric availability</h3>
              {data.metric_reasons.map((reason) => <p key={reason.code}>{reason.message}</p>)}
            </div>}
            <div className="space-y-1 text-xs text-slate-400">
              <h3 className="font-semibold text-slate-300">Advanced market-history prerequisites</h3>
              <p>{data.market_history.cache_gate_met ? "Cached thresholds met; validation still pending." : "Not ready for advanced proxy analytics."} This does not block snapshot or holdings analysis.</p>
              {data.market_history.reasons.map((reason) => <p key={reason}>{reason}</p>)}
            </div>
          </div>
        </details>
      </>}
  </section>;
}
