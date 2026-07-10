import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, Loader2, Wrench } from "lucide-react";
import { api } from "../lib/api";
import { MatchingAdmin } from "./MatchingAdmin";

export function MatchingWorkspace() {
  const [advanced, setAdvanced] = useState(false);
  const summaryQ = useQuery({ queryKey: ["matching-summary"], queryFn: api.getMatchingSummary });
  const summary = summaryQ.data;
  const issueCount = summary
    ? summary.orders_unmatched +
      summary.orders_auto_review +
      summary.instruments_with_reconciliation_issues
    : 0;
  const healthy = summary != null && issueCount === 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-white">Matching health</h1>
          <p className="mt-1 text-sm text-slate-500">
            Order-to-instrument links only need attention when an exception appears.
          </p>
        </div>
        {summary ? (
          <span className="chip chip-muted tabular">
            {summary.orders_matched}/{summary.orders_total} matched
          </span>
        ) : null}
      </div>

      {summaryQ.isLoading ? (
        <div className="glass flex min-h-40 items-center justify-center rounded-2xl text-sm text-slate-500">
          <Loader2 size={18} className="mr-2 animate-spin" /> Checking matching health…
        </div>
      ) : healthy ? (
        <div className="glass rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.04] p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-400/10">
              <CheckCircle2 size={18} className="text-emerald-300" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">Matching is healthy</h2>
              <p className="mt-1 text-xs text-slate-400">
                No unmatched orders, review candidates, or reconciliation exceptions need attention.
              </p>
            </div>
          </div>
        </div>
      ) : summary ? (
        <div className="glass rounded-2xl border border-amber-400/20 bg-amber-400/[0.04] p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-300" />
            <div>
              <h2 className="text-sm font-semibold text-white">{issueCount} matching exceptions</h2>
              <p className="mt-1 text-xs text-slate-400">
                {summary.orders_unmatched} unmatched · {summary.orders_auto_review} awaiting review · {summary.instruments_with_reconciliation_issues} reconciliation issues
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="glass rounded-2xl p-5 text-sm text-neg">
          Matching health could not be loaded.
        </div>
      )}

      <button
        type="button"
        onClick={() => setAdvanced((value) => !value)}
        className="flex min-h-10 items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 text-xs font-medium text-slate-300 hover:bg-white/[0.06]"
      >
        <Wrench size={14} />
        {advanced ? "Hide advanced matching tools" : "Open advanced matching tools"}
        <ChevronDown size={14} className={`transition-transform ${advanced ? "rotate-180" : ""}`} />
      </button>

      {advanced ? <MatchingAdmin /> : null}
    </div>
  );
}
