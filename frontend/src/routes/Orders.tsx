import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { StatCard } from "../components/StatCard";
import { OrderHistorySection } from "../components/OrderHistorySection";

export function Orders() {
  const { dripThreshold, accountFilter } = usePreferences();

  const ordersQ = useQuery({
    queryKey: ["orders", dripThreshold],
    queryFn: () => api.getOrders(dripThreshold),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
  });

  const analytics = analyticsQ.data;
  const orders = useMemo(
    () =>
      accountFilter === "all"
        ? (ordersQ.data ?? [])
        : (ordersQ.data ?? []).filter((order) => order.account_name === accountFilter),
    [accountFilter, ordersQ.data],
  );
  const filteredAnalytics = useMemo(() => {
    if (!analytics || accountFilter === "all") return analytics;
    let totalBuy = 0;
    let totalDrip = 0;
    let totalSell = 0;
    let buyCount = 0;
    let sellCount = 0;
    let dripCount = 0;
    const annualDrip = new Map<number, number>();
    for (const order of orders) {
      const cost = order.cost_proceeds_gbp ?? 0;
      const side = order.side.toLowerCase();
      if (side === "buy") {
        totalBuy += cost;
        buyCount += 1;
        if (order.is_drip) {
          totalDrip += cost;
          dripCount += 1;
          const year = new Date(order.order_date).getFullYear();
          annualDrip.set(year, (annualDrip.get(year) ?? 0) + cost);
        }
      } else if (side === "sell") {
        totalSell += cost;
        sellCount += 1;
      }
    }
    const cashDeployed = totalBuy - totalDrip;
    return {
      ...analytics,
      total_orders: orders.length,
      total_buy_gbp: totalBuy,
      total_drip_gbp: totalDrip,
      total_sell_gbp: totalSell,
      cash_deployed_gbp: cashDeployed,
      net_cash_invested_gbp: cashDeployed - totalSell,
      drip_count: dripCount,
      buy_count: buyCount,
      sell_count: sellCount,
      annual_drip: [...annualDrip.entries()]
        .sort(([a], [b]) => a - b)
        .map(([year, total_gbp]) => ({ year, total_gbp })),
      first_order_date: orders.at(-1)?.order_date ?? null,
    };
  }, [accountFilter, analytics, orders]);
  const hasOrders = (filteredAnalytics?.total_orders ?? 0) > 0;

  if (!hasOrders) {
    return (
      <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
        <Sparkles className="mx-auto text-aurora-cyan" size={28} />
        <h2 className="mt-3 text-lg font-semibold text-white">
          No orders imported yet
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Import an order history XLS to see your full transaction log and DRIP
          analysis.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1
          className="text-2xl font-semibold text-white"
          style={{ letterSpacing: "-0.02em" }}
        >
          Order history
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Complete order log with DRIP-aware classification.
        </p>
      </div>

      {filteredAnalytics && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Cash deployed"
            value={toGbp(filteredAnalytics.cash_deployed_gbp)}
            tone="accent"
            sub="Discretionary buys minus sells"
          />
          <StatCard
            label="DRIP reinvested"
            value={toGbp(filteredAnalytics.total_drip_gbp)}
            tone="amber"
            sub={`${filteredAnalytics.drip_count} DRIP orders`}
          />
          <StatCard
            label="Sale proceeds"
            value={toGbp(filteredAnalytics.total_sell_gbp)}
            tone="muted"
            sub={`${filteredAnalytics.sell_count} sell orders`}
          />
          <StatCard
            label="Total orders"
            value={String(filteredAnalytics.total_orders)}
            tone="muted"
            sub={
              filteredAnalytics.first_order_date
                ? `Since ${filteredAnalytics.first_order_date.slice(0, 7)}`
                : undefined
            }
          />
        </div>
      )}

      {filteredAnalytics && (
        <OrderHistorySection
          orders={orders}
          analytics={filteredAnalytics}
          dripThreshold={dripThreshold}
        />
      )}
    </div>
  );
}
