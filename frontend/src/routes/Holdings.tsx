import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { HoldingsTable } from "../components/HoldingsTable";
import {
  InstrumentDetail,
  InstrumentDetailEmpty,
} from "../components/InstrumentDetail";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

export function Holdings() {
  const [params, setParams] = useSearchParams();
  const { dripThreshold, accountFilter } = usePreferences();
  const selectedAccount = accountFilter === "all" ? undefined : accountFilter;
  const selectedRaw = params.get("inst");
  const selectedInstrument = selectedRaw ? Number(selectedRaw) : null;

  const setSelected = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("inst");
    else next.set("inst", String(id));
    setParams(next, { replace: true });
  };

  const instrumentsQ = useQuery({
    queryKey: ["instruments", selectedAccount],
    queryFn: () => api.getInstruments(selectedAccount),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold, accountFilter],
    queryFn: () => api.getOrderAnalytics(dripThreshold, selectedAccount),
  });
  const historyQ = useQuery({
    queryKey: ["instrument-history", selectedInstrument],
    queryFn: () => api.getInstrumentHistory(selectedInstrument as number),
    enabled: selectedInstrument !== null,
  });
  const instrOrdersQ = useQuery({
    queryKey: ["instrument-orders", selectedInstrument, dripThreshold],
    queryFn: () =>
      api.getInstrumentOrders(selectedInstrument as number, dripThreshold),
    enabled: selectedInstrument !== null,
  });
  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold, accountFilter],
    queryFn: () => api.getOrderPositions(dripThreshold, selectedAccount),
    enabled: (analyticsQ.data?.total_orders ?? 0) > 0,
  });
  const summaryQ = useQuery({ queryKey: ["summary", selectedAccount], queryFn: () => api.getSummary(selectedAccount) });

  const allInstruments = instrumentsQ.data ?? [];
  const instruments = useMemo(
    () =>
      accountFilter === "all"
        ? allInstruments
        : allInstruments.filter((instrument) => instrument.account_name === accountFilter),
    [accountFilter, allInstruments],
  );
  const groups = summaryQ.data?.group_allocation ?? [];
  const hasOrders = (analyticsQ.data?.total_orders ?? 0) > 0;

  const selectedName = useMemo(
    () =>
      instruments.find((i) => i.id === selectedInstrument)?.security_name ??
      null,
    [instruments, selectedInstrument],
  );
  const selectedHolding = useMemo(
    () => instruments.find((i) => i.id === selectedInstrument) ?? null,
    [instruments, selectedInstrument],
  );
  const selectedPosition = useMemo(
    () =>
      positionsQ.data?.find((position) => position.instrument_id === selectedInstrument) ??
      null,
    [positionsQ.data, selectedInstrument],
  );

  return (
    <div className="space-y-5">
      <MatchingWarningBanner />

      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-white" style={{ letterSpacing: "-0.02em" }}>
            Holdings
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            All instruments with current value and unrealised P&L.
          </p>
        </div>
        <span className="chip chip-muted tabular">
          {summaryQ.data?.position_count ?? "—"} positions in scope
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="min-w-0 lg:col-span-3">
          <HoldingsTable
            instruments={instruments}
            groups={groups}
            selectedId={selectedInstrument}
            onSelect={setSelected}
          />
        </div>
        <div className="min-w-0 lg:col-span-2">
          {selectedInstrument === null ? (
            <InstrumentDetailEmpty />
          ) : (
            <InstrumentDetail
              name={selectedName}
              instrument={selectedHolding}
              trailingDripYieldPct={selectedPosition?.trailing_drip_yield_pct ?? null}
              history={historyQ.data ?? []}
              historyLoading={historyQ.isLoading}
              orders={instrOrdersQ.data ?? []}
              ordersLoading={instrOrdersQ.isLoading}
              hasOrders={hasOrders}
            />
          )}
        </div>
      </div>
    </div>
  );
}
