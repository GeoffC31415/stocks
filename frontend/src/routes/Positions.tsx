import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { PositionAnalysis } from "../components/PositionAnalysis";
import { GroupPerformancePanel } from "../components/GroupPerformancePanel";
import { SegmentedControl, type Segment } from "../components/SegmentedControl";

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
  const positions = useMemo(() => {
    const rows = positionsQ.data ?? [];
    if (accountFilter === "all") return rows;
    return rows.filter(
      (position) =>
        position.instrument_id != null &&
        instrumentAccountById.get(position.instrument_id) === accountFilter,
    );
  }, [accountFilter, instrumentAccountById, positionsQ.data]);

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
          groups={groupPerfQ.data ?? []}
          isLoading={groupPerfQ.isLoading}
        />
      )}
    </div>
  );
}
