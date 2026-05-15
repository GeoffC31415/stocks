import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { PositionAnalysis } from "../components/PositionAnalysis";
import { GroupPerformancePanel } from "../components/GroupPerformancePanel";
import { SegmentedControl, type Segment } from "../components/SegmentedControl";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

type View = "positions" | "groups";

export function Positions() {
  const { dripThreshold, accountFilter } = usePreferences();
  const [view, setView] = useState<View>("positions");

  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold],
    queryFn: () => api.getOrderPositions(dripThreshold),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
  });
  const groupPerfQ = useQuery({
    queryKey: ["group-performance", dripThreshold],
    queryFn: () => api.getGroupPerformance(dripThreshold),
    enabled: view === "groups",
  });
  const instrumentsQ = useQuery({
    queryKey: ["instruments"],
    queryFn: api.getInstruments,
  });

  const hasOrders = (analyticsQ.data?.total_orders ?? 0) > 0;
  const instrumentAccountById = useMemo(
    () =>
      new Map(
        (instrumentsQ.data ?? []).map((instrument) => [
          instrument.id,
          instrument.account_name,
        ]),
      ),
    [instrumentsQ.data],
  );
  const positions = positionsQ.data ?? [];

  const filteredGroupPerformance = useMemo(() => {
    const groups = groupPerfQ.data ?? [];
    if (accountFilter === "all") return groups;
    return groups.map((group) => {
      const filteredMembers = group.members.filter(
        (m) => instrumentAccountById.get(m.instrument_id) === accountFilter,
      );
      const totalValue = filteredMembers.reduce((s, m) => s + (m.current_value_gbp ?? 0), 0);
      const totalCost = filteredMembers.reduce((s, m) => s + m.net_cost_gbp, 0);
      const totalPnl = filteredMembers.reduce((s, m) => s + (m.pnl_gbp ?? 0), 0);
      const pnlPct = totalCost !== 0 ? (totalPnl / totalCost) * 100 : null;
      // Recompute weighted CAGR from members
      const totalWeight = filteredMembers.reduce((s, m) => s + (m.current_value_gbp ?? 0), 0);
      let weightedCagr = 0;
      if (totalWeight > 0) {
        for (const m of filteredMembers) {
          const w = (m.current_value_gbp ?? 0) / totalWeight;
          if (m.annualised_return_pct != null) weightedCagr += w * m.annualised_return_pct;
        }
      }
      const earliestDate = filteredMembers
        .map((m) => m.first_order_date)
        .filter((d): d is string => d != null)
        .sort()[0] ?? null;
      return {
        ...group,
        members: filteredMembers,
        total_current_value_gbp: totalValue,
        total_net_cost_gbp: totalCost,
        total_pnl_gbp: totalPnl,
        pnl_pct: pnlPct,
        weighted_cagr_pct: totalWeight > 0 ? weightedCagr : null,
        earliest_order_date: earliestDate,
        members_with_value: filteredMembers.filter((m) => m.current_value_gbp != null).length,
      };
    });
  }, [accountFilter, groupPerfQ.data, instrumentAccountById]);

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

      {view === "positions" ? (
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
