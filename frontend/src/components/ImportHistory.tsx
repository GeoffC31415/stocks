import { Clock } from "lucide-react";
import type { ImportBatch } from "../lib/api";

export function ImportHistory({ imports }: { imports: ImportBatch[] }) {
  if (imports.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-slate-500">
        No imports yet.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {imports.slice(0, 12).map((entry) => (
        <li
          key={entry.id}
          className="rounded-lg border border-slate-700/40 bg-slate-900/30 p-3 transition-colors hover:bg-slate-900/50"
        >
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Clock size={12} />
            <span>Batch #{entry.id}</span>
            <span className="text-slate-600">·</span>
            <span className="text-cyan-400">{entry.as_of_date}</span>
          </div>
          <div className="mt-1 truncate text-sm text-slate-300">
            {entry.filename ?? "unknown.xls"}
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            {entry.diff_summary?.row_count ?? 0} rows · {entry.diff_summary?.new_instrument_ids?.length ?? 0} new · {entry.diff_summary?.closed?.length ?? 0} closed
          </div>
        </li>
      ))}
    </ul>
  );
}
