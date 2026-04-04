import { Card } from "./Card";
import { toGbp } from "../lib/formatters";
import type { PortfolioSummary, OrderAnalytics } from "../lib/api";

export function PortfolioCards({ summary }: { summary: PortfolioSummary }) {
  const pnl = summary.total_pnl_gbp;
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Card label="Portfolio value" value={toGbp(summary.total_value_gbp)} />
      <Card label="Book cost" value={toGbp(summary.total_book_cost_gbp)} />
      <Card
        label="Portfolio P&L"
        value={toGbp(pnl)}
        valueClass={pnl >= 0 ? "text-emerald-400" : "text-rose-400"}
      />
    </div>
  );
}

export function OrderAnalyticsCards({
  analytics,
  dripThreshold,
  effectiveReturn,
  effectiveReturnPct,
  annualisedReturnPct,
}: {
  analytics: OrderAnalytics;
  dripThreshold: number;
  effectiveReturn: number | null;
  effectiveReturnPct: number | null;
  annualisedReturnPct: number | null;
}) {
  const returnSub = [
    effectiveReturnPct !== null
      ? `${effectiveReturnPct >= 0 ? "+" : ""}${effectiveReturnPct.toFixed(1)}% on cash deployed`
      : null,
    annualisedReturnPct !== null
      ? `${annualisedReturnPct >= 0 ? "+" : ""}${annualisedReturnPct.toFixed(1)}% p.a.`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="Cash deployed"
        value={toGbp(analytics.cash_deployed_gbp)}
        sub="Discretionary buys, excl. DRIP"
      />
      <Card
        label="DRIP reinvested"
        value={toGbp(analytics.total_drip_gbp)}
        sub={`${analytics.drip_count} orders < ${toGbp(dripThreshold)}`}
        valueClass="text-amber-300"
      />
      <Card
        label="Sale proceeds"
        value={toGbp(analytics.total_sell_gbp)}
        sub={`${analytics.sell_count} sell orders`}
      />
      {effectiveReturn !== null && (
        <Card
          label="Effective return"
          value={toGbp(effectiveReturn)}
          sub={returnSub || undefined}
          valueClass={effectiveReturn >= 0 ? "text-emerald-400" : "text-rose-400"}
        />
      )}
    </div>
  );
}
