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

export function Holdings() {
  const [params, setParams] = useSearchParams();
  const { dripThreshold, accountFilter } = usePreferences();
  const selectedRaw = params.get("inst");
  const selectedInstrument = selectedRaw ? Number(selectedRaw) : null;

  const setSelected = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id == null) next.delete("inst");
    else next.set("inst", String(id));
    setParams(next, { replace: true });
  };

  const instrumentsQ = useQuery({
    queryKey: ["instruments"],
    queryFn: api.getInstruments,
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
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
    queryKey: ["positions", dripThreshold],
    queryFn: () => api.getOrderPositions(dripThreshold),
    enabled: (analyticsQ.data?.total_orders ?? 0) > 0,
  });
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: api.getGroups });

  const allInstruments = useMemo(() => instrumentsQ.data ?? [], [instrumentsQ.data]);
  const instruments = useMemo(
    () =>
      accountFilter === "all"
        ? allInstruments
        : allInstruments.filter((instrument) => instrument.account_name === accountFilter),
    [accountFilter, allInstruments],
  );
  const groups = groupsQ.data ?? [];
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
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white" style={{ letterSpacing: "-0.02em" }}>
            Holdings
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            All instruments with current value and unrealised P&L.
          </p>
        </div>
        <span className="chip chip-muted tabular">
          {instruments.length} positions
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <HoldingsTable
            instruments={instruments}
            groups={groups}
            selectedId={selectedInstrument}
            onSelect={setSelected}
          />
        </div>
        <div className="lg:col-span-2">
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
