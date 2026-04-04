import type { Instrument } from "../lib/api";
import { toGbp, pct } from "../lib/formatters";

export function HoldingsTable({
  instruments,
  selectedId,
  onSelect,
}: {
  instruments: Instrument[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-700/50 bg-slate-900/30">
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-900/95 backdrop-blur">
            <tr className="text-left text-xs font-medium uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3">Instrument</th>
              <th className="px-4 py-3 text-right">Value</th>
              <th className="px-4 py-3 text-right">P&amp;L</th>
              <th className="px-4 py-3 text-right">% Chg</th>
            </tr>
          </thead>
          <tbody>
            {instruments.map((inst) => {
              const isSelected = selectedId === inst.id;
              return (
                <tr
                  key={inst.id}
                  className={`cursor-pointer border-t border-slate-800/50 transition-colors hover:bg-slate-800/30 ${
                    isSelected ? "bg-cyan-900/20 hover:bg-cyan-900/25" : ""
                  }`}
                  onClick={() => onSelect(isSelected ? null : inst.id)}
                >
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-white">
                      {inst.identifier}
                    </div>
                    <div className="text-xs text-slate-500">
                      {inst.security_name}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-200">
                    {toGbp(inst.latest_value_gbp)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right font-medium ${
                      (inst.pnl_gbp ?? 0) >= 0
                        ? "text-emerald-400"
                        : "text-rose-400"
                    }`}
                  >
                    {toGbp(inst.pnl_gbp)}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right ${
                      (inst.latest_pct_change ?? 0) >= 0
                        ? "text-emerald-400"
                        : "text-rose-400"
                    }`}
                  >
                    {pct(inst.latest_pct_change)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
