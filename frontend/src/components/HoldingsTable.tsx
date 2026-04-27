import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { Instrument } from "../lib/api";
import { toGbp, pct } from "../lib/formatters";

type SortKey = "value" | "pnl" | "pct";

export function HoldingsTable({
  instruments,
  selectedId,
  onSelect,
}: {
  instruments: Instrument[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("value");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? instruments.filter(
          (i) =>
            i.security_name.toLowerCase().includes(q) ||
            i.identifier.toLowerCase().includes(q),
        )
      : instruments;
    return [...filtered].sort((a, b) => {
      if (sort === "pnl") return (b.pnl_gbp ?? 0) - (a.pnl_gbp ?? 0);
      if (sort === "pct")
        return (b.latest_pct_change ?? 0) - (a.latest_pct_change ?? 0);
      return (b.latest_value_gbp ?? 0) - (a.latest_value_gbp ?? 0);
    });
  }, [instruments, query, sort]);

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.05] px-4 py-3">
        <div className="relative flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            type="search"
            placeholder="Search instruments…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder:text-slate-600 focus:border-aurora-cyan/60 focus:outline-none"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-xs text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
        >
          <option value="value">Sort: value</option>
          <option value="pnl">Sort: P&amp;L</option>
          <option value="pct">Sort: % change</option>
        </select>
      </div>

      <div className="max-h-[560px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-aurora-base/85 backdrop-blur-md">
            <tr className="text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <th className="px-4 py-3">Instrument</th>
              <th className="px-4 py-3 text-right">Value</th>
              <th className="px-4 py-3 text-right">P&amp;L</th>
              <th className="px-4 py-3 text-right">% Chg</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((inst, idx) => {
              const isSelected = selectedId === inst.id;
              const isPos = (inst.pnl_gbp ?? 0) >= 0;
              const isPctPos = (inst.latest_pct_change ?? 0) >= 0;
              return (
                <tr
                  key={inst.id}
                  className={`relative cursor-pointer border-t border-white/[0.04] transition-colors ${
                    isSelected
                      ? "bg-gradient-to-r from-violet-500/10 to-cyan-500/10"
                      : idx % 2 === 0
                        ? "bg-white/[0.012]"
                        : ""
                  } hover:bg-white/[0.04]`}
                  onClick={() => onSelect(isSelected ? null : inst.id)}
                >
                  <td className="relative px-4 py-2.5">
                    {isSelected && (
                      <span
                        aria-hidden
                        className="absolute left-0 top-1 bottom-1 w-[2px] rounded-r bg-aurora-accent"
                      />
                    )}
                    <div className="font-medium text-white">
                      {inst.identifier}
                    </div>
                    <div className="truncate text-xs text-slate-500">
                      {inst.security_name}
                    </div>
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-slate-200">
                    {toGbp(inst.latest_value_gbp)}
                  </td>
                  <td
                    className={`tabular px-4 py-2.5 text-right font-medium ${
                      isPos ? "text-pos" : "text-neg"
                    }`}
                  >
                    {toGbp(inst.pnl_gbp)}
                  </td>
                  <td
                    className={`tabular px-4 py-2.5 text-right ${
                      isPctPos ? "text-pos" : "text-neg"
                    }`}
                  >
                    {pct(inst.latest_pct_change)}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-xs text-slate-500">
                  No instruments match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
