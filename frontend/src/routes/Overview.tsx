import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2, Sparkles, Wallet, Banknote } from "lucide-react";
import { api } from "../lib/api";
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

      <ChartPanel
        cashflow={cashflowQ.data ?? []}
        timeseries={timeseriesQ.data ?? []}
        estimatedTimeseries={estimatedQ.data ?? []}
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
