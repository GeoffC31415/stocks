import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Loader2 } from "lucide-react";
import { api } from "./lib/api";
import { toGbp, DRIP_DEFAULT } from "./lib/formatters";
import { Collapsible } from "./components/Collapsible";
import { PortfolioCards, OrderAnalyticsCards } from "./components/SummaryCards";
import { ChartPanel } from "./components/ChartPanel";
import { ImportPanel } from "./components/ImportPanel";
import { PerformersSection } from "./components/PerformersSection";
import { HoldingsTable } from "./components/HoldingsTable";
import { InstrumentDetail, InstrumentDetailEmpty } from "./components/InstrumentDetail";
import { OrderHistorySection } from "./components/OrderHistorySection";
import { PositionAnalysis } from "./components/PositionAnalysis";
import { GroupsSection } from "./components/GroupsSection";
import { ImportHistory } from "./components/ImportHistory";

export default function App() {
  const [dripThreshold, setDripThreshold] = useState(DRIP_DEFAULT);
  const [dripInput, setDripInput] = useState(String(DRIP_DEFAULT));
  const [selectedInstrument, setSelectedInstrument] = useState<number | null>(null);

  const applyDrip = () => {
    const parsed = parseFloat(dripInput);
    if (!isNaN(parsed) && parsed >= 0) setDripThreshold(parsed);
  };

  // ── Queries ──
  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.getSummary });
  const timeseriesQ = useQuery({ queryKey: ["timeseries"], queryFn: api.getTimeseries });
  const instrumentsQ = useQuery({ queryKey: ["instruments"], queryFn: api.getInstruments });
  const importsQ = useQuery({ queryKey: ["imports"], queryFn: api.getImports });
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: api.getGroups });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
  });
  const ordersQ = useQuery({
    queryKey: ["orders", dripThreshold],
    queryFn: () => api.getOrders(dripThreshold),
  });
  const historyQ = useQuery({
    queryKey: ["instrument-history", selectedInstrument],
    queryFn: () => api.getInstrumentHistory(selectedInstrument as number),
    enabled: selectedInstrument !== null,
  });
  const cashflowQ = useQuery({
    queryKey: ["cashflow", dripThreshold],
    queryFn: () => api.getCashflowTimeseries(dripThreshold),
  });
  const estimatedQ = useQuery({
    queryKey: ["estimated-timeseries"],
    queryFn: api.getEstimatedTimeseries,
    enabled: (analyticsQ.data?.total_orders ?? 0) > 0,
  });
  const positionsQ = useQuery({
    queryKey: ["positions", dripThreshold],
    queryFn: () => api.getOrderPositions(dripThreshold),
  });
  const instrOrdersQ = useQuery({
    queryKey: ["instrument-orders", selectedInstrument, dripThreshold],
    queryFn: () => api.getInstrumentOrders(selectedInstrument as number, dripThreshold),
    enabled: selectedInstrument !== null,
  });

  // ── Derived data ──
  const instruments = instrumentsQ.data ?? [];
  const groups = groupsQ.data ?? [];
  const analytics = analyticsQ.data;
  const hasOrders = (analytics?.total_orders ?? 0) > 0;

  const byGroup = useMemo(() => {
    const grouped: Record<number, typeof instruments> = {};
    for (const group of groups) {
      grouped[group.id] = instruments.filter((i) => i.group_ids.includes(group.id));
    }
    return grouped;
  }, [groups, instruments]);

  const selectedInstrumentName = useMemo(
    () => instruments.find((i) => i.id === selectedInstrument)?.security_name ?? null,
    [instruments, selectedInstrument],
  );

  const effectiveReturn = useMemo(() => {
    if (!analytics || !summaryQ.data) return null;
    return summaryQ.data.total_value_gbp + analytics.total_sell_gbp - analytics.cash_deployed_gbp;
  }, [analytics, summaryQ.data]);

  const effectiveReturnPct = useMemo(() => {
    if (!analytics || analytics.cash_deployed_gbp === 0 || effectiveReturn === null) return null;
    return (effectiveReturn / analytics.cash_deployed_gbp) * 100;
  }, [analytics, effectiveReturn]);

  const annualisedReturnPct = useMemo(() => {
    if (!analytics || !summaryQ.data || analytics.cash_deployed_gbp <= 0 || !analytics.first_order_date) return null;
    const endValue = summaryQ.data.total_value_gbp + analytics.total_sell_gbp;
    const startValue = analytics.cash_deployed_gbp;
    if (endValue <= 0) return null;
    const first = new Date(analytics.first_order_date);
    const now = new Date();
    const years = (now.getTime() - first.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
    if (years < 0.25) return null;
    return ((endValue / startValue) ** (1.0 / years) - 1.0) * 100.0;
  }, [analytics, summaryQ.data]);

  const loading =
    summaryQ.isLoading || timeseriesQ.isLoading || instrumentsQ.isLoading ||
    groupsQ.isLoading || importsQ.isLoading;

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <Loader2 size={24} className="animate-spin" />
          <span className="text-lg">Loading portfolio data…</span>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* ── Header ── */}
      <header className="mb-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-lg shadow-cyan-500/20">
            <BarChart3 size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Portfolio tracker
            </h1>
            <p className="text-xs text-slate-500">
              Barclays XLS snapshots · order history · DRIP-adjusted returns
            </p>
          </div>
        </div>
      </header>

      <div className="space-y-5">
        {/* ── Summary cards (always visible, no collapsible) ── */}
        {summaryQ.data && <PortfolioCards summary={summaryQ.data} />}
        {hasOrders && analytics && (
          <OrderAnalyticsCards
            analytics={analytics}
            dripThreshold={dripThreshold}
            effectiveReturn={effectiveReturn}
            effectiveReturnPct={effectiveReturnPct}
            annualisedReturnPct={annualisedReturnPct}
          />
        )}

        {/* ── Charts + Import ── */}
        <section className="grid gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <ChartPanel
              cashflow={cashflowQ.data ?? []}
              timeseries={timeseriesQ.data ?? []}
              estimatedTimeseries={estimatedQ.data ?? []}
              hasOrders={hasOrders}
            />
          </div>
          <div className="lg:col-span-2">
            <ImportPanel
              dripThreshold={dripThreshold}
              dripInput={dripInput}
              setDripInput={setDripInput}
              onApplyDrip={applyDrip}
            />
          </div>
        </section>

        {/* ── Performers ── */}
        <Collapsible
          title="Performance leaders"
          subtitle="Top and bottom movers by percentage change"
        >
          <PerformersSection
            worst={summaryQ.data?.worst_pct ?? []}
            best={summaryQ.data?.best_pct ?? []}
            onSelect={setSelectedInstrument}
          />
        </Collapsible>

        {/* ── Holdings + Instrument detail ── */}
        <Collapsible
          title="Holdings"
          subtitle="All instruments with current value and P&L"
          badge={
            <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-slate-300">
              {instruments.length}
            </span>
          }
        >
          <div className="grid gap-5 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <HoldingsTable
                instruments={instruments}
                selectedId={selectedInstrument}
                onSelect={setSelectedInstrument}
              />
            </div>
            <div className="lg:col-span-2">
              {selectedInstrument === null ? (
                <InstrumentDetailEmpty />
              ) : (
                <InstrumentDetail
                  name={selectedInstrumentName}
                  history={historyQ.data ?? []}
                  historyLoading={historyQ.isLoading}
                  orders={instrOrdersQ.data ?? []}
                  ordersLoading={instrOrdersQ.isLoading}
                  hasOrders={hasOrders}
                />
              )}
            </div>
          </div>
        </Collapsible>

        {/* ── Order history (only when orders exist) ── */}
        {hasOrders && analytics && (
          <Collapsible
            title="Order history & DRIP"
            subtitle="Complete order log with DRIP income analysis"
            badge={
              <span className="rounded-full bg-amber-900/50 px-2.5 py-0.5 text-xs font-medium text-amber-300">
                {analytics.total_orders} orders
              </span>
            }
          >
            <OrderHistorySection
              orders={ordersQ.data ?? []}
              analytics={analytics}
              dripThreshold={dripThreshold}
            />
          </Collapsible>
        )}

        {/* ── Position analysis ── */}
        {hasOrders && (
          <Collapsible
            title="Position analysis"
            subtitle="Cost basis & returns derived from order history"
          >
            <PositionAnalysis positions={positionsQ.data ?? []} />
          </Collapsible>
        )}

        {/* ── Groups + Import history ── */}
        <section className="grid gap-5 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Collapsible
              title="Groups"
              subtitle="Organise instruments into custom groups"
              defaultOpen={false}
            >
              <GroupsSection
                groups={groups}
                instruments={instruments}
                byGroup={byGroup}
              />
            </Collapsible>
          </div>
          <div>
            <Collapsible
              title="Import history"
              subtitle="Recent portfolio snapshot imports"
              defaultOpen={false}
            >
              <ImportHistory imports={importsQ.data ?? []} />
            </Collapsible>
          </div>
        </section>
      </div>
    </main>
  );
}
