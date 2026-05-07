import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { api } from "../lib/api";
import { Link } from "react-router-dom";

export function MatchingWarningBanner() {
  const summaryQ = useQuery({
    queryKey: ["matching-summary"],
    queryFn: api.getMatchingSummary,
    staleTime: 60_000,
  });

  const summary = summaryQ.data;
  if (!summary || summary.orders_unmatched === 0) return null;

  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
      <AlertTriangle size={16} className="mt-0.5 text-amber-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-amber-300/90">
          {summary.orders_unmatched} of {summary.orders_total} orders are unmatched.
          Cost basis and position analytics may be incomplete.
        </p>
        <Link
          to="/matching"
          className="inline-flex items-center gap-1 text-[11px] text-amber-400/70 hover:text-amber-300 mt-1"
        >
          Resolve in Matching Admin
          <ArrowRight size={10} />
        </Link>
      </div>
    </div>
  );
}
