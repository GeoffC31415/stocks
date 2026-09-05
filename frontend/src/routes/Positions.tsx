import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { PositionAnalysis } from "../components/PositionAnalysis";
import { GroupPerformancePanel } from "../components/GroupPerformancePanel";
import { SegmentedControl, type Segment } from "../components/SegmentedControl";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

type View = "positions" | "groups";

export function Positions() {
  const { dripThreshold, accountFilter } = usePreferences();
  const selectedAccount = accountFilter === "all" ? undefined : accountFilter;
  const [view, setView] = useState<View>("positions");

  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold, accountFilter],
    queryFn: () => api.getOrderPositions(dripThreshold, selectedAccount),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold, accountFilter],
    queryFn: () => api.getOrderAnalytics(dripThreshold, selectedAccount),
  });
  const groupPerfQ = useQuery({
    queryKey: ["group-performance", dripThreshold,selectedAccount],
    queryFn: () => api.getGroupPerformance(dripThreshold,selectedAccount),
    enabled: view === "groups",
  });
  const hasOrders = (analyticsQ.data?.total_orders ?? 0) > 0;
  const positions = positionsQ.data ?? [];
  const filteredGroupPerformance=groupPerfQ.data??[];

  const viewSegments: Segment<View>[] = [
    { key: "positions", label: "By position" },
    { key: "groups", label: "By group" },
  ];

  return (
    <div className="space-y-5">
      <MatchingWarningBanner />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1
            className="text-2xl font-semibold text-white"
            style={{ letterSpacing: "-0.02em" }}
          >
            {view === "positions" ? "Position analysis" : "Group performance"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {view === "positions"
              ? "Cost basis & returns derived from order history."
              : "Combined cost, value, P&L and CAGR per group — with rebased growth comparison."}
          </p>
        </div>
        <SegmentedControl
          layoutId="positions-view"
          value={view}
          onChange={setView}
          tone={view === "positions" ? "accent" : "violet"}
          segments={viewSegments}
        />
      </div>

      {analyticsQ.isError || positionsQ.isError || (view==="groups" && groupPerfQ.isError) ? <div role="alert" className="min-h-96">Unable to load returns. <button onClick={()=>{void analyticsQ.refetch();void positionsQ.refetch();void groupPerfQ.refetch();}}>Retry returns</button></div> : analyticsQ.isPending || positionsQ.isPending ? <div role="status" className="min-h-96">Loading returns…</div> : !hasOrders ? <div className="min-h-96"><h2>No positions yet</h2><p>Import order history to derive cost basis and returns.</p></div> : view === "positions" ? (
        <PositionAnalysis positions={positions} />
      ) : (
        <GroupPerformancePanel
          groups={filteredGroupPerformance}
          isLoading={groupPerfQ.isLoading}
        />
      )}
    </div>
  );
}
