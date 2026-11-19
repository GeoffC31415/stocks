import { useState } from "react";
import { api } from "../lib/api";
import { SyncEvidence } from "./SyncEvidence";
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
  try {
    const value = Number(localStorage.getItem(STORAGE));
    return TOLERANCES.includes(value) ? value : 14;
  } catch {
    return 14;
  }
}
const dateLabel = (date: string | null) => (date ? formatOrderDate(date) : "Not recorded");

export function DataConfidencePanel({ compact = false }: { compact?: boolean }) {
  const { accountFilter } = usePreferences();
  const syncQ = useQuery({ queryKey: ["syncStatus"], queryFn: api.getSyncStatus, retry: false });
  const { period } = useAnalysisScope();
  const [staleDays, setStaleDays] = useState(storedTolerance);
  const account = accountFilter === "all" ? undefined : accountFilter;
  const query = useQuery({
    queryKey: ["data-confidence", account, period, staleDays],
    queryFn: () => dataQualityApi.getConfidence(account, period, staleDays),
  });
  const data = query.data;
  const critical = data?.attention.filter((item) => item.severity === "critical") ?? [];
  const reminders = data?.attention.filter((item) => item.severity !== "critical") ?? [];

  const maxAge = data?.snapshots.length ? Math.max(...data.snapshots.map((s) => s.age_days)) : null;
  const firstClass = data ? Object.values(data.classification)[0] : undefined;

  return (
    <section
      className="border-t border-white/[0.09] pt-3 [overflow-wrap:anywhere]"
      aria-label="Data confidence"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 className="tufte-label">Data telemetry</h2>
          {data && (
            <div className="num flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-400">
              <span>{data.snapshots.length} accts · max age {maxAge ?? "—"}d</span>
              <span>·</span>
              <span>{data.transactions.count} txns</span>
              {firstClass && firstClass.holding_count > 0 && (
                <>
                  <span>·</span>
                  <span>{firstClass.classified_value_pct.toFixed(0)}% classified</span>
                </>
              )}
              <span>·</span>
              <span className={data.attention.length === 0 ? "text-emerald-400" : "text-amber-300"}>
                {data.attention.length} {data.attention.length === 1 ? "alert" : "alerts"}
              </span>
            </div>
          )}
        </div>
        {!compact && (syncQ.data || syncQ.isError) && (
          <SyncEvidence
            report={syncQ.data?.last_run ?? syncQ.data}
            compact={compact}
            unavailable={syncQ.isError}
            onRetry={() => void syncQ.refetch()}
          />
        )}
      </div>

      {query.isLoading ? (
        <p role="status" className="mt-1.5 text-xs text-slate-500">Checking recorded data…</p>
      ) : query.isError ? (
        <AnalysisStatus kind="error" title="Unable to check data confidence." onRetry={() => void query.refetch()} />
      ) : (
        data && (
          <>
            {critical.length > 0 && <div className="mt-2"><AttentionList items={critical} /></div>}
            <details open={!compact} className="mt-1.5">
              <summary className="cursor-pointer text-[11px] text-slate-400 hover:text-slate-200">
                {data.attention.length === 0
                  ? "Core data checks healthy — view coverage and limitations"
                  : `${data.attention.length} data check${data.attention.length === 1 ? "" : "s"} need attention — view evidence`}
              </summary>
              <div className="mt-3 grid gap-4 border-t border-white/[0.06] pt-3 sm:grid-cols-2 lg:grid-cols-4">
                {reminders.length > 0 && (
                  <div className="sm:col-span-2 lg:col-span-4">
                    <AttentionList items={reminders} />
                  </div>
                )}
                <div className="space-y-1 text-xs text-slate-400">
                  <h3 className="tufte-label">Snapshot freshness</h3>
                  {data.snapshots.map((row) => (
                    <p key={row.account_name} className="num">
                      {row.account_name}: {dateLabel(row.date)} ({row.age_days}d)
                    </p>
                  ))}
                  <label className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
                    Tolerance
                    <select
                      aria-label="Snapshot freshness tolerance"
                      className="num rounded-sm border border-white/[0.1] bg-[#0e1117] px-1.5 py-0.5 text-[11px] text-slate-200"
                      value={staleDays}
                      onChange={(event) => {
                        const value = Number(event.target.value);
                        setStaleDays(value);
                        try { localStorage.setItem(STORAGE, String(value)); } catch { /* Optional */ }
                      }}
                    >
                      {TOLERANCES.map((days) => <option key={days} value={days}>{days}d</option>)}
                    </select>
                  </label>
                </div>
                <div className="space-y-1 text-xs text-slate-400">
                  <h3 className="tufte-label">Transactions</h3>
                  <p className="num">{data.transactions.count} rows · {dateLabel(data.transactions.first_date)} – {dateLabel(data.transactions.last_date)}</p>
                  <p className="text-[11px] text-slate-500">Completeness is unknown; unrecorded flows cannot be inferred as zero.</p>
                </div>
                <div className="space-y-1 text-xs text-slate-400">
                  <h3 className="tufte-label">Classification</h3>
                  {Object.entries(data.classification).map(([dimension, coverage]) => (
                    <p key={dimension} className="num">
                      {dimension.replace("_", " ")}: {coverage.holding_count
                        ? `${coverage.classified_count}/${coverage.holding_count} (${coverage.classified_value_pct.toFixed(1)}%)`
                        : "None"}
                    </p>
                  ))}
                </div>
                <div className="space-y-1 text-xs text-slate-400">
                  <h3 className="tufte-label">Market history</h3>
                  <p>{data.market_history.cache_gate_met ? "Cache gate met (validation pending)." : "Not ready for proxy analytics (does not block snapshot or holdings analysis)."}</p>
                  {data.metric_reasons.map((reason) => <p key={reason.code} className="text-amber-300">{reason.message}</p>)}
                </div>
              </div>
            </details>
          </>
        )
      )}
    </section>
  );
}
