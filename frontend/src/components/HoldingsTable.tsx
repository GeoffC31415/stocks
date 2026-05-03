import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { Instrument } from "../lib/api";
import { toGbp, pct } from "../lib/formatters";

type SortKey = "value" | "pnl" | "pct" | "delta";

const formatSignedGbp = (value: number | null): string => {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${toGbp(value)}`;
};

const formatSignedQty = (value: number | null): string => {
  if (value == null) return "—";
  const abs = Math.abs(value);
  const formatted = abs >= 100 ? abs.toFixed(0) : abs.toFixed(abs >= 1 ? 2 : 4);
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatted}`;
};

const hasMeaningfulDelta = (value: number | null): boolean =>
  value != null && Math.abs(value) >= 0.005;

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
      if (sort === "delta")
        return (
          Math.abs(b.delta_value_gbp_since_prev_snapshot ?? 0) -
          Math.abs(a.delta_value_gbp_since_prev_snapshot ?? 0)
        );
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
          <option value="delta">Sort: Δ vs prev</option>
        </select>
      </div>

      <div className="max-h-[560px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-aurora-base/85 backdrop-blur-md">
            <tr className="text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <th className="px-4 py-3">Instrument</th>
              <th className="px-4 py-3 text-right">Value</th>
              <th
                className="px-4 py-3 text-right"
                title="Change in value since the previous snapshot"
              >
                Δ vs prev
              </th>
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
                    <div className="mt-1 flex flex-wrap gap-1">
                      {inst.asset_class ? (
                        <span className="text-[10px] text-slate-600">{inst.asset_class}</span>
                      ) : null}
                      {inst.sector ? (
                        <span className="text-[10px] text-slate-600">· {inst.sector}</span>
                      ) : null}
                      {inst.ticker ? (
                        <span className="text-[10px] text-slate-600">· {inst.ticker}</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="tabular px-4 py-2.5 text-right text-slate-200">
                    {toGbp(inst.latest_value_gbp)}
                    {inst.latest_quote_price_gbp != null ? (
                      <div className="text-[10px] text-slate-600">
                        quote {toGbp(inst.latest_quote_price_gbp)}
                      </div>
                    ) : null}
                  </td>
                  <td className="tabular px-4 py-2.5 text-right">
                    <DeltaCell
                      deltaValue={inst.delta_value_gbp_since_prev_snapshot}
                      deltaQty={inst.delta_quantity_since_prev_snapshot}
                    />
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
                <td colSpan={5} className="px-4 py-8 text-center text-xs text-slate-500">
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

function DeltaCell({
  deltaValue,
  deltaQty,
}: {
  deltaValue: number | null;
  deltaQty: number | null;
}) {
  if (deltaValue == null) {
    return <span className="text-slate-600">—</span>;
  }
  const isMeaningful = hasMeaningfulDelta(deltaValue);
  const tone = !isMeaningful
    ? "text-slate-500"
    : deltaValue > 0
      ? "text-pos"
      : "text-neg";
  const showQty = hasMeaningfulDelta(deltaQty);
  return (
    <>
      <div className={`font-medium ${tone}`}>{formatSignedGbp(deltaValue)}</div>
      {showQty ? (
        <div className="text-[10px] text-slate-600">
          qty {formatSignedQty(deltaQty)}
        </div>
      ) : null}
    </>
  );
}
