import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2, Sparkles, Wallet, Banknote } from "lucide-react";
import { api, formatSnapshotDateIso, type AllocationRow, type ImportDiffSummary } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { HeroKpi } from "../components/HeroKpi";
import { StatCard } from "../components/StatCard";
import { ChartPanel } from "../components/ChartPanel";
import { PerformersSection } from "../components/PerformersSection";

export function Overview() {
  const navigate = useNavigate();
  const { dripThreshold } = usePreferences();

  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.getSummary });
  const timeseriesQ = useQuery({
    queryKey: ["timeseries"],
    queryFn: api.getTimeseries,
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
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
  const importDiffQ = useQuery({
    queryKey: ["import-diff", summaryQ.data?.import_batch_id],
    queryFn: () => api.getImportDiff(summaryQ.data?.import_batch_id as number),
    enabled: summaryQ.data?.import_batch_id != null,
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

  const valueTrendPct = useMemo(() => {
    const data = estimatedQ.data ?? [];
    if (data.length < 2) return null;
    const last = data[data.length - 1].estimated_value_gbp;
    const yearAgo =
      data.length >= 13
        ? data[data.length - 13].estimated_value_gbp
        : data[0].estimated_value_gbp;
    if (!yearAgo) return null;
    return ((last - yearAgo) / yearAgo) * 100;
  }, [estimatedQ.data]);

  const valueDeltaAbs = useMemo(() => {
    const data = estimatedQ.data ?? [];
    if (data.length < 2) return null;
    const last = data[data.length - 1].estimated_value_gbp;
    const yearAgo =
      data.length >= 13
        ? data[data.length - 13].estimated_value_gbp
        : data[0].estimated_value_gbp;
    return last - yearAgo;
  }, [estimatedQ.data]);

  const effectiveReturn = useMemo(() => {
    if (!analytics || !summary) return null;
    return summary.total_value_gbp + analytics.total_sell_gbp - analytics.cash_deployed_gbp;
  }, [analytics, summary]);

  const effectiveReturnPct = useMemo(() => {
    if (!analytics || !effectiveReturn || analytics.cash_deployed_gbp === 0) return null;
    return (effectiveReturn / analytics.cash_deployed_gbp) * 100;
  }, [analytics, effectiveReturn]);

  const annualisedReturnPct = useMemo(() => {
    if (!analytics || !summary || analytics.cash_deployed_gbp <= 0 || !analytics.first_order_date) return null;
    const endValue = summary.total_value_gbp + analytics.total_sell_gbp;
    const startValue = analytics.cash_deployed_gbp;
    if (endValue <= 0) return null;
    const first = new Date(analytics.first_order_date);
    const now = new Date();
    const years = (now.getTime() - first.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
    if (years < 0.25) return null;
    return ((endValue / startValue) ** (1.0 / years) - 1.0) * 100.0;
  }, [analytics, summary]);

  const effReturnSparkline = useMemo(() => {
    const est = estimatedQ.data ?? [];
    const flow = cashflowQ.data ?? [];
    if (est.length === 0 || flow.length === 0) return [];
    const byMonth = new Map(flow.map((c) => [c.month, c]));
    return est
      .slice(-24)
      .map((p) => {
        const cf = byMonth.get(p.month);
        const deployed = cf?.cumulative_net_deployed ?? 0;
        const sells = cf?.cumulative_sells ?? 0;
        return {
          month: p.month,
          value: p.estimated_value_gbp + sells - deployed,
        };
      });
  }, [estimatedQ.data, cashflowQ.data]);

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

  if (!summary || summary.total_value_gbp === 0) {
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
      <HeroKpi
        label="Portfolio value"
        value={summary.total_value_gbp}
        trendPct={valueTrendPct}
        deltaAbs={valueDeltaAbs}
        sparkline={valueSparkline}
        caption={hasOrders ? "vs. 12 months ago" : undefined}
      />

      <WhatChangedCard diff={importDiffQ.data ?? null} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Portfolio P&L"
          value={toGbp(summary.total_pnl_gbp)}
          tone={summary.total_pnl_gbp >= 0 ? "pos" : "neg"}
          sub={`Book cost ${toGbp(summary.total_book_cost_gbp)}`}
          sparkline={pnlSparkline.length > 1 ? pnlSparkline : undefined}
          sparklineKey="value"
        />
        {hasOrders && analytics && effectiveReturn != null ? (
          <StatCard
            label="Effective return"
            value={toGbp(effectiveReturn)}
            tone={effectiveReturn >= 0 ? "pos" : "neg"}
            trend={effectiveReturnPct ?? null}
            trendFormat={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
            sub={
              annualisedReturnPct != null
                ? `${annualisedReturnPct >= 0 ? "+" : ""}${annualisedReturnPct.toFixed(1)}% p.a.`
                : "on cash deployed"
            }
            sparkline={effReturnSparkline}
            sparklineKey="value"
            icon={<Sparkles size={14} />}
          />
        ) : (
          <StatCard
            label="Book cost"
            value={toGbp(summary.total_book_cost_gbp)}
            tone="muted"
            sub="From latest snapshot"
            icon={<Wallet size={14} />}
          />
        )}
        {hasOrders && analytics ? (
          <StatCard
            label="Cash deployed"
            value={toGbp(analytics.cash_deployed_gbp)}
            tone="accent"
            sub={`${analytics.buy_count} discretionary buys`}
            sparkline={cashSparkline}
            sparklineKey="value"
            icon={<Banknote size={14} />}
          />
        ) : (
          <StatCard
            label="Holdings"
            value={String(Object.keys(summary.by_account).length || 0)}
            tone="accent"
            sub="Unique accounts"
          />
        )}
      </div>

      {hasOrders && analytics && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="DRIP reinvested"
            value={toGbp(analytics.total_drip_gbp)}
            tone="amber"
            sub={`${analytics.drip_count} orders < ${toGbp(dripThreshold)}`}
          />
          <StatCard
            label="Sale proceeds"
            value={toGbp(analytics.total_sell_gbp)}
            tone="muted"
            sub={`${analytics.sell_count} sell orders`}
          />
          <StatCard
            label="Total orders"
            value={String(analytics.total_orders)}
            tone="muted"
            sub={
              analytics.first_order_date
                ? `Since ${analytics.first_order_date.slice(0, 7)}`
                : undefined
            }
          />
        </div>
      )}

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
            Top and bottom movers by % change.
          </p>
        </div>
        <PerformersSection
          worst={summary.worst_pct ?? []}
          best={summary.best_pct ?? []}
          onSelect={(id) => navigate(`/holdings?inst=${id}`)}
        />
      </div>
    </div>
  );
}

function WhatChangedCard({ diff }: { diff: ImportDiffSummary | null }) {
  if (!diff || diff.previous_batch_id == null) return null;

  const topMovers = [...diff.changed]
    .sort((a, b) => Math.abs(b.delta_value_gbp ?? 0) - Math.abs(a.delta_value_gbp ?? 0))
    .slice(0, 3);

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            What changed
          </p>
          <h2 className="mt-1 text-sm font-semibold text-white">
            Since{" "}
            {diff.previous_as_of_date
              ? formatSnapshotDateIso(diff.previous_as_of_date)
              : `batch ${diff.previous_batch_id}`}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => {
            window.location.href = `/diff?from=${diff.previous_batch_id}&to=${diff.batch_id}`;
          }}
          className="chip chip-muted"
        >
          Open diff
        </button>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <ChangeStat label="New" value={diff.new_instrument_ids.length} />
        <ChangeStat label="Closed" value={diff.closed.length} />
        <ChangeStat label="Changed" value={diff.changed.length} />
      </div>
      {topMovers.length > 0 ? (
        <div className="mt-4 space-y-2">
          {topMovers.map((mover) => {
            const delta = mover.delta_value_gbp ?? 0;
            return (
              <div key={mover.instrument_id} className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-slate-200">
                    {mover.identifier}
                  </p>
                  <p className="truncate text-[11px] text-slate-600">
                    {mover.security_name ?? mover.account_name}
                  </p>
                </div>
                <div className={`tabular text-right text-xs font-semibold ${delta >= 0 ? "text-pos" : "text-neg"}`}>
                  {delta >= 0 ? "+" : ""}
                  {toGbp(delta)}
                  <p className="font-normal text-slate-500">
                    qty {mover.quantity_before ?? "—"} → {mover.quantity_after ?? "—"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ChangeStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className="tabular text-lg font-semibold text-white">{value}</p>
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
        <div className="space-y-2">
          {topHoldings.map((row) => (
            <AllocationBar key={row.label} label={row.label} value={row.weight_pct} />
          ))}
        </div>
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
