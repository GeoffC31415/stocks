import { useMemo } from "react";
import { parseInstrumentId } from "../lib/holdingsView";
import { HoldingDetailPanel } from "../components/HoldingDetailPanel";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useTargetDrift } from "../state/useTargetDrift";
import { usePreferences } from "../state/usePreferences";
import { HoldingsTable } from "../components/HoldingsTable";
import {
  InstrumentDetail,
  InstrumentDetailEmpty,
} from "../components/InstrumentDetail";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

export function Holdings() {
  const [params, setParams] = useSearchParams();
  const {query:targetsQ}=useTargetDrift();
  const { dripThreshold, accountFilter } = usePreferences();
  const selectedAccount = accountFilter === "all" ? undefined : accountFilter;
  const selectedRaw = params.get("inst");
  const selectedInstrument = parseInstrumentId(params);

  const setSelected = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("inst");
    else next.set("inst", String(id));
    setParams(next);
  };

  const instrumentsQ = useQuery({
    queryKey: ["instruments", selectedAccount],
    queryFn: () => api.getInstruments(selectedAccount),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold, accountFilter],
    queryFn: () => api.getOrderAnalytics(dripThreshold, selectedAccount),
  });
  const confirmed = selectedInstrument !== null && (instrumentsQ.data ?? []).some(i => i.id === selectedInstrument && (selectedAccount === undefined || i.account_name === selectedAccount));
  const historyQ = useQuery({
    queryKey: ["instrument-history", selectedInstrument, selectedAccount],
    queryFn: () => api.getInstrumentHistory(selectedInstrument as number),
    enabled: confirmed,
  });
  const instrOrdersQ = useQuery({
    queryKey: ["instrument-orders", selectedInstrument, dripThreshold, selectedAccount],
    queryFn: () =>
      api.getInstrumentOrders(selectedInstrument as number, dripThreshold),
    enabled: confirmed,
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
            scopeTotalValue={summaryQ.data?.total_value_gbp}
            groups={groups}
            targetDrift={targetsQ.isError || targetsQ.isFetching ? undefined : targetsQ.data}
            selectedId={selectedInstrument}
            onSelect={setSelected}
          />
        </div>
        <div className="min-w-0 lg:col-span-2">
          {selectedRaw !== null && !confirmed ? (
            <div role="alert">{selectedInstrument === null ? "Invalid instrument selection." : instrumentsQ.isPending ? "Checking instrument account scope…" : "Instrument not available in the selected account. Clear the selection or change account."}<button type="button" onClick={()=>setSelected(null)}>Clear selection</button></div>
          ) : selectedInstrument === null ? (
            <InstrumentDetailEmpty />
          ) : (
            <HoldingDetailPanel instrumentId={selectedInstrument} onClose={()=>setSelected(null)}><InstrumentDetail
              name={selectedName}
              instrument={selectedHolding}
              trailingDripYieldPct={selectedPosition?.trailing_drip_yield_pct ?? null}
              history={historyQ.data ?? []}
              historyLoading={historyQ.isLoading}
              orders={instrOrdersQ.data ?? []}
              ordersLoading={instrOrdersQ.isLoading}
              hasOrders={hasOrders || confirmed}
              historyError={historyQ.isError}
              ordersError={instrOrdersQ.isError}
              onRetryHistory={()=>{void historyQ.refetch();}}
              onRetryOrders={()=>{void instrOrdersQ.refetch();}}
            /></HoldingDetailPanel>
          )}
        </div>
      </div>
    </div>
  );
}
