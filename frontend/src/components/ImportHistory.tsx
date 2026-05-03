import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, Clock, FileSpreadsheet } from "lucide-react";
import { api, type ImportBatch } from "../lib/api";
import { usePreferences } from "../state/usePreferences";
import { formatOrderDate, toGbp } from "../lib/formatters";

export function ImportHistory({ imports }: { imports: ImportBatch[] }) {
  const { dripThreshold } = usePreferences();
  const unlinkedQ = useQuery({
    queryKey: ["unlinked-orders", dripThreshold],
    queryFn: () => api.getUnlinkedOrders(dripThreshold),
  });

  if (imports.length === 0) {
    return (
      <div className="space-y-4">
        <UnlinkedOrdersCard
          count={unlinkedQ.data?.count ?? 0}
          orders={unlinkedQ.data?.orders ?? []}
          isLoading={unlinkedQ.isLoading}
        />
        <div className="glass rounded-2xl p-6 text-center">
          <Clock size={20} className="mx-auto text-slate-600" />
          <p className="mt-2 text-sm text-slate-400">No imports yet</p>
          <p className="mt-1 text-xs text-slate-500">
            Snapshots you import will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <UnlinkedOrdersCard
        count={unlinkedQ.data?.count ?? 0}
        orders={unlinkedQ.data?.orders ?? []}
        isLoading={unlinkedQ.isLoading}
      />
      <div className="glass rounded-2xl p-5">
        <div className="mb-3 flex items-center gap-2">
          <Clock size={14} className="text-slate-500" />
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-300">
            Recent imports
          </h3>
          <span className="ml-auto text-[10px] text-slate-600">
            Latest {Math.min(imports.length, 12)}
          </span>
        </div>
        <ul className="space-y-2">
          {imports.slice(0, 12).map((entry) => {
            const newCount = entry.diff_summary?.new_instrument_ids?.length ?? 0;
            const closedCount = entry.diff_summary?.closed?.length ?? 0;
            const rowCount = entry.diff_summary?.row_count ?? 0;
            return (
              <li
                key={entry.id}
                className="rounded-xl border border-white/[0.04] bg-white/[0.02] p-3 transition-colors hover:border-white/[0.08] hover:bg-white/[0.04]"
              >
                <div className="flex items-center gap-2 text-[11px] text-slate-500">
                  <span className="chip chip-muted tabular">#{entry.id}</span>
                  <span className="tabular text-aurora-cyan">
                    {entry.as_of_date}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-1.5 truncate text-sm text-slate-200">
                  <FileSpreadsheet size={12} className="shrink-0 text-slate-500" />
                  <span className="truncate">
                    {entry.filename ?? "unknown.xls"}
                  </span>
                </div>
                <div className="tabular mt-1 flex flex-wrap gap-3 text-[11px] text-slate-500">
                  <span>{rowCount} rows</span>
                  {newCount > 0 && (
                    <span className="text-pos">+{newCount} new</span>
                  )}
                  {closedCount > 0 && (
                    <span className="text-neg">-{closedCount} closed</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

function UnlinkedOrdersCard({
  count,
  orders,
  isLoading,
}: {
  count: number;
  orders: import("../lib/api").Order[];
  isLoading: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (isLoading || count === 0) return null;

  const visible = isExpanded ? orders : orders.slice(0, 5);
  const hiddenCount = orders.length - visible.length;

  return (
    <div className="glass rounded-2xl border border-amber-400/20 bg-amber-500/[0.04] p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-400/[0.12]">
          <AlertTriangle size={14} className="text-amber-300" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-300/80">
            Unlinked orders
          </p>
          <p className="mt-0.5 text-sm font-semibold text-white">
            {count} order{count === 1 ? "" : "s"} not matched to any instrument
          </p>
          <p className="mt-1 text-[11px] text-slate-400">
            These are absent from per-position analytics. Set the matching ticker
            or identifier on the instrument and re-import to fix.
          </p>
          {orders.length > 0 ? (
            <button
              type="button"
              onClick={() => setIsExpanded((v) => !v)}
              className="mt-2 flex items-center gap-1 text-[11px] font-medium text-amber-200 transition-colors hover:text-amber-100"
            >
              <ChevronDown
                size={12}
                className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
              />
              {isExpanded ? "Hide" : `Show ${Math.min(orders.length, 5)} most recent`}
            </button>
          ) : null}
        </div>
      </div>
      {orders.length > 0 && isExpanded ? (
        <ul className="mt-3 space-y-1.5">
          {visible.map((order) => (
            <li
              key={order.id}
              className="flex items-center gap-2 rounded-md bg-white/[0.02] px-2.5 py-1.5 text-[11px]"
            >
              <span className="chip chip-muted tabular shrink-0">
                {formatOrderDate(order.order_date)}
              </span>
              <span className="truncate text-slate-200">{order.security_name}</span>
              <span
                className={`tabular ml-auto shrink-0 ${
                  order.side.toLowerCase() === "sell" ? "text-neg" : "text-slate-400"
                }`}
              >
                {order.side.toUpperCase()} {toGbp(order.cost_proceeds_gbp)}
              </span>
            </li>
          ))}
          {hiddenCount > 0 ? (
            <li className="px-2.5 text-[11px] text-slate-500">
              +{hiddenCount} more not shown.
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
