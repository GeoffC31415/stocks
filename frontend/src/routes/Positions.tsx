import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { PositionAnalysis } from "../components/PositionAnalysis";

export function Positions() {
  const { dripThreshold } = usePreferences();

  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold],
    queryFn: () => api.getOrderPositions(dripThreshold),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
  });

  const hasOrders = (analyticsQ.data?.total_orders ?? 0) > 0;

  if (!hasOrders) {
    return (
      <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
        <Sparkles className="mx-auto text-aurora-cyan" size={28} />
        <h2 className="mt-3 text-lg font-semibold text-white">
          No positions yet
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Import order history to derive cost basis and CAGR per position.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1
          className="text-2xl font-semibold text-white"
          style={{ letterSpacing: "-0.02em" }}
        >
          Position analysis
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Cost basis & returns derived from order history.
        </p>
      </div>

      <PositionAnalysis positions={positionsQ.data ?? []} />
    </div>
  );
}
