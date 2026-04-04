import { useMemo, useState } from "react";
import type { PositionSummary } from "../lib/api";
import { toGbp } from "../lib/formatters";

type PositionTab = "open" | "closed";
type PositionSort = "net_cost" | "pnl" | "return_pct";

export function PositionAnalysis({
  positions,
}: {
  positions: PositionSummary[];
}) {
  const [tab, setTab] = useState<PositionTab>("open");
  const [sort, setSort] = useState<PositionSort>("net_cost");

  const openCount = positions.filter((p) => !p.is_closed).length;
  const closedCount = positions.filter((p) => p.is_closed).length;

  const sorted = useMemo(() => {
    const filtered = positions.filter((p) =>
      tab === "open" ? !p.is_closed : p.is_closed,
    );
    return [...filtered].sort((a, b) => {
      if (sort === "pnl") {
        const pa =
          (a.estimated_pnl_gbp ?? a.realized_pnl_gbp) ?? -Infinity;
        const pb =
          (b.estimated_pnl_gbp ?? b.realized_pnl_gbp) ?? -Infinity;
        return pb - pa;
      }
      if (sort === "return_pct") {
        const ra = a.annualised_return_pct ?? -Infinity;
        const rb = b.annualised_return_pct ?? -Infinity;
        return rb - ra;
      }
      return Math.abs(b.net_cost_gbp) - Math.abs(a.net_cost_gbp);
    });
  }, [positions, tab, sort]);

  const closedPnlTotal = useMemo(
    () =>
      positions
        .filter((p) => p.is_closed)
        .reduce((s, p) => s + (p.realized_pnl_gbp ?? 0), 0),
    [positions],
  );

  return (
    <div>
      {/* Controls */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as PositionSort)}
          className="rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
        >
          <option value="net_cost">Sort: net cost</option>
          <option value="pnl">Sort: P&amp;L £</option>
          <option value="return_pct">Sort: CAGR</option>
        </select>

        <div className="flex rounded-lg border border-slate-700 bg-slate-900/60 p-0.5">
          <button
            type="button"
            onClick={() => setTab("open")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              tab === "open"
                ? "bg-cyan-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Open ({openCount})
          </button>
          <button
            type="button"
            onClick={() => setTab("closed")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              tab === "closed"
                ? "bg-violet-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Closed ({closedCount})
          </button>
        </div>
      </div>

      {tab === "closed" && (
        <div className="mb-3 flex items-center gap-4 rounded-lg bg-slate-900/40 px-4 py-2 text-sm">
          <span className="text-slate-400">Total realized P&amp;L</span>
          <span
            className={`font-bold ${
              closedPnlTotal >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {closedPnlTotal >= 0 ? "+" : ""}
            {toGbp(closedPnlTotal)}
          </span>
        </div>
      )}

      <div className="overflow-auto rounded-xl border border-slate-700/40 bg-slate-900/20">
        <div className="max-h-[480px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-900/95 backdrop-blur text-left text-xs font-medium uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-4 py-2.5">Security</th>
                <th className="px-4 py-2.5 text-right">Discretionary</th>
                {tab === "open" && (
                  <th className="px-4 py-2.5 text-right">DRIP</th>
                )}
                <th className="px-4 py-2.5 text-right">Sells</th>
                <th className="px-4 py-2.5 text-right">Net cost</th>
                {tab === "open" ? (
                  <>
                    <th className="px-4 py-2.5 text-right">Current value</th>
                    <th className="px-4 py-2.5 text-right">P&amp;L</th>
                    <th className="px-4 py-2.5 text-right">CAGR</th>
                  </>
                ) : (
                  <th className="px-4 py-2.5 text-right">Realized P&amp;L</th>
                )}
                <th className="px-4 py-2.5 text-right text-slate-600">Since</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => {
                const pnl =
                  tab === "open"
                    ? p.estimated_pnl_gbp
                    : p.realized_pnl_gbp;
                const pnlClass =
                  (pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400";
                const dash = (
                  <span className="text-slate-700">—</span>
                );
                return (
                  <tr
                    key={p.security_name}
                    className="border-t border-slate-800/50 transition-colors hover:bg-slate-800/20"
                  >
                    <td className="px-4 py-2.5">
                      <div
                        className="max-w-[220px] truncate font-medium text-white"
                        title={p.security_name}
                      >
                        {p.security_name}
                      </div>
                      <div className="text-xs text-slate-500">
                        {p.order_count} orders · {p.drip_count} DRIP
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-300">
                      {toGbp(p.discretionary_buy_gbp)}
                    </td>
                    {tab === "open" && (
                      <td className="px-4 py-2.5 text-right text-amber-400">
                        {p.total_drip_gbp > 0
                          ? toGbp(p.total_drip_gbp)
                          : dash}
                      </td>
                    )}
                    <td className="px-4 py-2.5 text-right text-slate-300">
                      {p.total_sell_gbp > 0
                        ? toGbp(p.total_sell_gbp)
                        : dash}
                    </td>
                    <td className="px-4 py-2.5 text-right font-medium text-white">
                      {toGbp(p.net_cost_gbp)}
                    </td>
                    {tab === "open" ? (
                      <>
                        <td className="px-4 py-2.5 text-right text-slate-300">
                          {p.current_value_gbp != null ? (
                            toGbp(p.current_value_gbp)
                          ) : (
                            <span className="text-xs text-slate-600">
                              no snapshot
                            </span>
                          )}
                        </td>
                        <td
                          className={`px-4 py-2.5 text-right font-semibold ${pnlClass}`}
                        >
                          {pnl != null ? (
                            (pnl >= 0 ? "+" : "") + toGbp(pnl)
                          ) : (
                            <span className="text-xs text-slate-600">—</span>
                          )}
                        </td>
                        <td
                          className={`px-4 py-2.5 text-right font-semibold ${
                            p.annualised_return_pct != null
                              ? (p.annualised_return_pct ?? 0) >= 0
                                ? "text-emerald-400"
                                : "text-rose-400"
                              : ""
                          }`}
                        >
                          {p.annualised_return_pct != null ? (
                            `${p.annualised_return_pct >= 0 ? "+" : ""}${p.annualised_return_pct.toFixed(1)}%/yr`
                          ) : (
                            <span className="text-xs text-slate-600">—</span>
                          )}
                        </td>
                      </>
                    ) : (
                      <td
                        className={`px-4 py-2.5 text-right font-semibold ${pnlClass}`}
                      >
                        {pnl != null ? (
                          (pnl >= 0 ? "+" : "") + toGbp(pnl)
                        ) : (
                          <span className="text-xs text-slate-600">—</span>
                        )}
                      </td>
                    )}
                    <td className="px-4 py-2.5 text-right text-xs text-slate-600">
                      {p.first_order_date.slice(0, 7)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
