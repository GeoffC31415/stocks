import { useMemo, useState } from "react";
import type { PositionSummary } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { SegmentedControl, type Segment } from "./SegmentedControl";

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

  const tabSegments: Segment<PositionTab>[] = [
    { key: "open", label: "Open", count: openCount },
    { key: "closed", label: "Closed", count: closedCount },
  ];

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          layoutId="position-tab"
          value={tab}
          onChange={setTab}
          tone={tab === "open" ? "accent" : "violet"}
          segments={tabSegments}
        />

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as PositionSort)}
          className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-xs text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
        >
          <option value="net_cost">Sort: net cost</option>
          <option value="pnl">Sort: P&amp;L £</option>
          <option value="return_pct">Sort: CAGR</option>
        </select>
      </div>

      {tab === "closed" && (
        <div className="mb-3 flex items-center gap-3 rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-2.5 text-sm">
          <span className="text-slate-400">Total realized P&amp;L</span>
          <span
            className={`tabular ml-auto font-bold ${
              closedPnlTotal >= 0 ? "text-pos" : "text-neg"
            }`}
          >
            {closedPnlTotal >= 0 ? "+" : ""}
            {toGbp(closedPnlTotal)}
          </span>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-white/[0.04]">
        <div className="max-h-[560px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-aurora-base/85 backdrop-blur-md text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="px-4 py-3">Security</th>
                <th className="px-4 py-3 text-right">Discretionary</th>
                {tab === "open" && <th className="px-4 py-3 text-right">DRIP</th>}
                <th className="px-4 py-3 text-right">Sells</th>
                <th className="px-4 py-3 text-right">Net cost</th>
                {tab === "open" ? (
                  <>
                    <th className="px-4 py-3 text-right">Current value</th>
                    <th className="px-4 py-3 text-right">P&amp;L</th>
                    <th className="px-4 py-3 text-right">CAGR</th>
                  </>
                ) : (
                  <th className="px-4 py-3 text-right">Realized P&amp;L</th>
                )}
                <th className="px-4 py-3 text-right text-slate-700">Since</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, idx) => {
                const pnl =
                  tab === "open" ? p.estimated_pnl_gbp : p.realized_pnl_gbp;
                const pnlClass = (pnl ?? 0) >= 0 ? "text-pos" : "text-neg";
                const dash = <span className="text-slate-700">—</span>;
                return (
                  <tr
                    key={p.security_name}
                    className={`border-t border-white/[0.04] transition-colors hover:bg-white/[0.04] ${
                      idx % 2 === 0 ? "bg-white/[0.012]" : ""
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <div
                        className="max-w-[240px] truncate font-medium text-white"
                        title={p.security_name}
                      >
                        {p.security_name}
                      </div>
                      <div className="text-xs text-slate-500">
                        {p.order_count} orders · {p.drip_count} DRIP
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-slate-300">
                      {toGbp(p.discretionary_buy_gbp)}
                    </td>
                    {tab === "open" && (
                      <td className="tabular px-4 py-2.5 text-right text-amber-300">
                        {p.total_drip_gbp > 0 ? toGbp(p.total_drip_gbp) : dash}
                      </td>
                    )}
                    <td className="tabular px-4 py-2.5 text-right text-slate-300">
                      {p.total_sell_gbp > 0 ? toGbp(p.total_sell_gbp) : dash}
                    </td>
                    <td className="tabular px-4 py-2.5 text-right font-medium text-white">
                      {toGbp(p.net_cost_gbp)}
                    </td>
                    {tab === "open" ? (
                      <>
                        <td className="tabular px-4 py-2.5 text-right text-slate-300">
                          {p.current_value_gbp != null ? (
                            toGbp(p.current_value_gbp)
                          ) : (
                            <span className="text-xs text-slate-700">no snapshot</span>
                          )}
                        </td>
                        <td className={`tabular px-4 py-2.5 text-right font-semibold ${pnlClass}`}>
                          {pnl != null ? (
                            (pnl >= 0 ? "+" : "") + toGbp(pnl)
                          ) : (
                            dash
                          )}
                        </td>
                        <td
                          className={`tabular px-4 py-2.5 text-right font-semibold ${
                            p.annualised_return_pct != null
                              ? (p.annualised_return_pct ?? 0) >= 0
                                ? "text-pos"
                                : "text-neg"
                              : ""
                          }`}
                        >
                          {p.annualised_return_pct != null
                            ? `${p.annualised_return_pct >= 0 ? "+" : ""}${p.annualised_return_pct.toFixed(1)}%/yr`
                            : dash}
                        </td>
                      </>
                    ) : (
                      <td className={`tabular px-4 py-2.5 text-right font-semibold ${pnlClass}`}>
                        {pnl != null ? (pnl >= 0 ? "+" : "") + toGbp(pnl) : dash}
                      </td>
                    )}
                    <td className="px-4 py-2.5 text-right text-xs text-slate-700">
                      {p.first_order_date.slice(0, 7)}
                    </td>
                  </tr>
                );
              })}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={tab === "open" ? 8 : 7} className="px-4 py-8 text-center text-xs text-slate-500">
                    No {tab} positions.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
