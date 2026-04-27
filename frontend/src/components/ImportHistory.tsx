import { Clock, FileSpreadsheet } from "lucide-react";
import type { ImportBatch } from "../lib/api";

export function ImportHistory({ imports }: { imports: ImportBatch[] }) {
  if (imports.length === 0) {
    return (
      <div className="glass rounded-2xl p-6 text-center">
        <Clock size={20} className="mx-auto text-slate-600" />
        <p className="mt-2 text-sm text-slate-400">No imports yet</p>
        <p className="mt-1 text-xs text-slate-500">
          Snapshots you import will appear here.
        </p>
      </div>
    );
  }

  return (
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
  );
}
