import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { StatCard } from "../components/StatCard";
import { OrderHistorySection } from "../components/OrderHistorySection";

export function Orders() {
  const { dripThreshold } = usePreferences();

  const ordersQ = useQuery({
    queryKey: ["orders", dripThreshold],
    queryFn: () => api.getOrders(dripThreshold),
  });
  const analyticsQ = useQuery({
    queryKey: ["order-analytics", dripThreshold],
    queryFn: () => api.getOrderAnalytics(dripThreshold),
  });

  const analytics = analyticsQ.data;
  const hasOrders = (analytics?.total_orders ?? 0) > 0;

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

      {analytics && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Cash deployed"
            value={toGbp(analytics.cash_deployed_gbp)}
            tone="accent"
            sub="Discretionary buys minus sells"
          />
          <StatCard
            label="DRIP reinvested"
            value={toGbp(analytics.total_drip_gbp)}
            tone="amber"
            sub={`${analytics.drip_count} DRIP orders`}
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

      {analytics && (
        <OrderHistorySection
          orders={ordersQ.data ?? []}
          analytics={analytics}
          dripThreshold={dripThreshold}
        />
      )}
    </div>
  );
}
