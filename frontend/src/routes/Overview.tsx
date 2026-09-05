import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { scopedNavigationUrl } from "../routing";
import { useAnalysisScope } from "../state/useAnalysisScope";
import { CalendarClock, Loader2, Sparkles, Wallet, Banknote } from "lucide-react";
import { api, formatSnapshotDateIso, type AllocationRow } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { HeroKpi } from "../components/HeroKpi";
import { StatCard } from "../components/StatCard";
import { ChartPanel } from "../components/ChartPanel";
import { PerformersSection } from "../components/PerformersSection";
import { PortfolioReturnCard } from "../components/PortfolioReturnCard";
import { AttributionSummaryCard } from "../components/AttributionSummaryCard";
import { PerformancePanel } from "../components/PerformancePanel";
import { AnalysisStatus } from "../components/AnalysisStatus";

export function Overview() {
  const navigate = useNavigate();
  const location = useLocation();
  const { period } = useAnalysisScope();
  const { dripThreshold, accountFilter } = usePreferences();
  const selectedAccount = accountFilter === "all" ? undefined : accountFilter;

  const summaryQ = useQuery({ queryKey: ["summary", selectedAccount], queryFn: () => api.getSummary(selectedAccount) });
  const returnsQ = useQuery({
    queryKey: ["portfolio-returns", accountFilter, period],
    queryFn: () => api.getPortfolioReturns(selectedAccount, undefined, undefined, period),
  });
  const timeseriesQ = useQuery({
    queryKey: ["timeseries", accountFilter],
    queryFn: () => api.getTimeseries(accountFilter === "all" ? undefined : accountFilter),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold, accountFilter],
    queryFn: () => api.getOrderAnalytics(dripThreshold, selectedAccount),
  });
  const cashflowQ = useQuery({
    queryKey: ["cashflow", dripThreshold, accountFilter],
    queryFn: () => api.getCashflowTimeseries(dripThreshold, selectedAccount),
  });
  const estimatedQ = useQuery({
    queryKey: ["estimated-timeseries", accountFilter],
    queryFn: () => api.getEstimatedTimeseries(accountFilter === "all" ? undefined : accountFilter),
    enabled: (analyticsQ.data?.total_orders ?? 0) > 0,
  });
  const attributionQ = useQuery({
    queryKey: ["snapshot-attribution", accountFilter],
    queryFn: () => api.getSnapshotAttribution(selectedAccount),
  });
  const benchmarkStart = estimatedQ.data?.[0]?.month
    ? `${estimatedQ.data[0].month}-01`
    : undefined;
  const benchmarkBaseValue = estimatedQ.data?.[0]?.estimated_value_gbp;
  const benchmarksQ = useQuery({
    queryKey: ["benchmarks", benchmarkStart, benchmarkBaseValue],
    queryFn: () =>
      api.getBenchmarks(["spx.us", "vwrl.uk"], benchmarkStart, benchmarkBaseValue),
    enabled:
      (analyticsQ.data?.total_orders ?? 0) > 0 &&
      benchmarkStart != null &&
      benchmarkBaseValue != null,
  });

  const summary = summaryQ.data;
  const valuationDates = summary?.scope?.valuation_dates.map((row) => row.date).sort() ?? [];
  const snapshotDateRange = { earliest: valuationDates[0] ?? null, latest: valuationDates[valuationDates.length - 1] ?? null };
  const analytics = analyticsQ.data;
  const hasOrders = (analytics?.total_orders ?? 0) > 0;

  const valueSparkline = useMemo(() => {
    const data = estimatedQ.data ?? [];
    if (data.length === 0) return [];
    return data.slice(-24).map((p) => ({
      month: p.month,
      value: p.estimated_value_gbp,
    }));
  }, [estimatedQ.data]);
  const valueSparklineCaption = useMemo(() => {
    if (valueSparkline.length === 0) return "Latest snapshot";
    const first = String(valueSparkline[0].month);
    const last = String(valueSparkline[valueSparkline.length - 1].month);
    return `Latest snapshot · order-derived trend ${first}–${last}`;
  }, [valueSparkline]);

  const pnlSparkline = useMemo(() => {
    const data = timeseriesQ.data ?? [];
    return data.map((p) => ({
      as_of_date: p.as_of_date,
      value: p.total_value_gbp - p.total_book_cost_gbp,
    }));
  }, [timeseriesQ.data]);

  const cashSparkline = useMemo(() => {
    const data = cashflowQ.data ?? [];
    return data.slice(-24).map((p) => ({
      month: p.month,
      value: p.cumulative_net_deployed,
    }));
  }, [cashflowQ.data]);

  if (summaryQ.isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-400">
        <Loader2 size={20} className="mr-2 animate-spin" />
        <span className="text-sm">Loading portfolio…</span>
      </div>
    );
  }

  if (summaryQ.isError) {
    return <AnalysisStatus kind="error" title="Unable to load portfolio summary. No balance is shown."
      onRetry={() => void summaryQ.refetch()} />;
  }

  if (selectedAccount && summary?.position_count === 0) {
    return <AnalysisStatus kind="empty" title="No holdings for the selected account."
      reasons={[{ code: "empty_account", message: "Choose another account or import a snapshot for this account.", action_href: "/data?tab=import" }]} />;
  }

  if (!summary || summary.as_of_date == null) {
    return (
      <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
        <Sparkles className="mx-auto text-aurora-cyan" size={28} />
        <h2 className="mt-3 text-lg font-semibold text-white">
          Welcome to your portfolio
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Import a Barclays snapshot to start tracking value, P&L and DRIP-aware
          returns.
        </p>
        <button
          type="button"
          onClick={() => navigate("/import")}
          className="btn-primary mt-5"
        >
          Import data
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-xs text-slate-400">Performance and portfolio return use the selected period, ending at the latest covered valuation.
        Current holdings use latest snapshots; order summaries and reconstruction use all recorded history.
        Attribution is the latest snapshot comparison, independent of the performance period.</p>
      <HeroKpi
        label="Portfolio value"
        value={summary.total_value_gbp}
        trendPct={null}
        deltaAbs={null}
        sparkline={valueSparkline}
        caption={valueSparklineCaption}
      />

      <SnapshotStalenessChip
        asOfDate={summary.latest_snapshot_date ?? summary.as_of_date}
        earliestAsOfDate={accountFilter === "all" ? snapshotDateRange.earliest : null}
        latestAsOfDate={accountFilter === "all" ? snapshotDateRange.latest : null}
      />

      {summary.scope?.warnings.map((warning) => <p key={warning} role="status" className="text-sm text-amber-200">{warning}</p>)}
      {analyticsQ.isError && <AnalysisStatus kind="error" title="Unable to load order analysis." onRetry={() => void analyticsQ.refetch()} />}
      {timeseriesQ.isError && <AnalysisStatus kind="error" title="Unable to load snapshot history." onRetry={() => void timeseriesQ.refetch()} />}
      {cashflowQ.isError && <AnalysisStatus kind="error" title="Unable to load cash-flow history." onRetry={() => void cashflowQ.refetch()} />}
      {estimatedQ.isError && <AnalysisStatus kind="error" title="Unable to load order-derived reconstruction." onRetry={() => void estimatedQ.refetch()} />}
      {attributionQ.isError
        ? <AnalysisStatus kind="error" title="Unable to load snapshot attribution." onRetry={() => void attributionQ.refetch()} />
        : <AttributionSummaryCard attribution={attributionQ.data ?? null} />}

      <PerformancePanel accountName={selectedAccount} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <PortfolioReturnCard summary={returnsQ.data} loading={returnsQ.isLoading}
          error={returnsQ.isError} onRetry={() => void returnsQ.refetch()} />
        <StatCard
          label="Portfolio P&L"
          value={toGbp(summary.total_pnl_gbp)}
          tone={summary.total_pnl_gbp >= 0 ? "pos" : "neg"}
          sub="Unrealised gain on invested holdings · cash excluded"
          sparkline={pnlSparkline.length > 1 ? pnlSparkline : undefined}
          sparklineKey="value"
        />
        <StatCard
          label="Book cost"
          value={toGbp(summary.total_book_cost_gbp)}
          tone="muted"
          sub="Cost recorded in the latest snapshots"
          icon={<Wallet size={14} />}
        />
        {hasOrders && analytics ? (
          <StatCard
            label="Cash deployed"
            value={toGbp(analytics.cash_deployed_gbp)}
            tone="accent"
            sub={`${analytics.buy_count} discretionary buys · account filtered`}
            sparkline={cashSparkline}
            sparklineKey="value"
            icon={<Banknote size={14} />}
          />
        ) : (
          <StatCard
            label="Accounts"
            value={String(Object.keys(summary.by_account).length || 0)}
            tone="accent"
            sub="Included in this view"
          />
        )}
      </div>

      <AllocationPanel
        allocation={summary.allocation ?? []}
        groups={summary.group_allocation ?? []}
      />

      <ChartPanel
        cashflow={cashflowQ.data ?? []}
        timeseries={timeseriesQ.data ?? []}
        estimatedTimeseries={estimatedQ.data ?? []}
        benchmarks={benchmarksQ.data ?? []}
        hasOrders={hasOrders}
      />

      <div>
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-base font-semibold text-white">
            Performance leaders
          </h2>
          <p className="text-xs text-slate-500">
            Highest and lowest holding returns against recorded book cost.
          </p>
        </div>
        <PerformersSection
          worst={(summary.worst_pct ?? []).slice(0, 5)}
          best={(summary.best_pct ?? []).slice(0, 5)}
          onSelect={(id) => navigate(scopedNavigationUrl(`/holdings?inst=${id}`, location.search))}
        />
      </div>
    </div>
  );
}

function SnapshotStalenessChip({
  asOfDate,
  earliestAsOfDate,
  latestAsOfDate,
}: {
  asOfDate: string | null;
  earliestAsOfDate: string | null;
  latestAsOfDate: string | null;
}) {
  const showRange = Boolean(
    earliestAsOfDate && latestAsOfDate && earliestAsOfDate !== latestAsOfDate,
  );
  const displayDate = showRange ? latestAsOfDate : asOfDate;
  if (!displayDate) return null;
  const rangeStart = earliestAsOfDate ?? displayDate;
  const rangeEnd = latestAsOfDate ?? displayDate;

  const parts = displayDate.split("-").map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return null;
  const [y, m, d] = parts;
  const snapshot = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  snapshot.setHours(0, 0, 0, 0);
  const days = Math.max(
    0,
    Math.round((today.getTime() - snapshot.getTime()) / (24 * 60 * 60 * 1000)),
  );

  let ageLabel: string;
  if (days === 0) ageLabel = "today";
  else if (days === 1) ageLabel = "1 day old";
  else ageLabel = `${days} days old`;

  const isStale = days >= 14;
  const toneClass = isStale
    ? "border-amber-400/30 bg-amber-400/[0.08] text-amber-200"
    : "border-white/[0.06] bg-white/[0.02] text-slate-400";

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] ${toneClass}`}
    >
      <CalendarClock size={12} />
      {showRange ? (
        <>
          <span className="tabular">
            Snapshot {formatSnapshotDateIso(rangeStart)} → {formatSnapshotDateIso(rangeEnd)}
          </span>
          <span className="text-slate-500">·</span>
          <span className="tabular font-medium">{ageLabel}</span>
        </>
      ) : (
        <>
          <span className="tabular">
            Snapshot from {formatSnapshotDateIso(displayDate)}
          </span>
          <span className="text-slate-500">·</span>
          <span className="tabular font-medium">{ageLabel}</span>
        </>
      )}
    </div>
  );
}

function AllocationPanel({
  allocation,
  groups,
}: {
  allocation: AllocationRow[];
  groups: AllocationRow[];
}) {
  const topHoldings = allocation.slice(0, 6);
  const risky = topHoldings.find((row) => row.is_concentration_risk);

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Allocation</h2>
          <p className="mt-1 text-xs text-slate-500">
            Position concentration and group target drift from the latest snapshot.
          </p>
        </div>
        {risky ? (
          <span className="rounded-full border border-amber-400/30 bg-amber-400/[0.08] px-3 py-1 text-xs font-medium text-amber-200">
            Concentration risk: {risky.label} at {risky.weight_pct.toFixed(1)}%
          </span>
        ) : null}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Largest holdings
          </p>
          <div className="space-y-2">
            {topHoldings.map((row) => (
              <AllocationBar key={row.label} label={row.label} value={row.weight_pct} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Portfolio groups
          </p>
          <div className="space-y-2">
            {groups.length === 0 ? (
              <p className="rounded-xl bg-white/[0.02] p-3 text-xs text-slate-500">
                Add groups and optional targets to track allocation drift.
              </p>
            ) : (
              groups.map((row) => (
                <AllocationBar
                  key={row.label}
                  label={row.label}
                  value={row.weight_pct}
                  target={row.target_pct}
                  drift={row.drift_pct}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function AllocationBar({
  label,
  value,
  target,
  drift,
}: {
  label: string;
  value: number;
  target?: number | null;
  drift?: number | null;
}) {
  return (
    <div className="rounded-xl bg-white/[0.02] p-3">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="truncate font-medium text-slate-200">{label}</span>
        <span className="tabular text-slate-400">
          {value.toFixed(1)}%
          {target != null ? ` / target ${target.toFixed(1)}%` : ""}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full bg-aurora-accent" style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
      {drift != null ? (
        <p className={`mt-1 tabular text-[11px] ${drift >= 0 ? "text-amber-200" : "text-slate-500"}`}>
          Drift {drift >= 0 ? "+" : ""}
          {drift.toFixed(1)} pts
        </p>
      ) : null}
    </div>
  );
}
