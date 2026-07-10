import { useQuery } from "@tanstack/react-query";
import { Clock3 } from "lucide-react";
import { ImportHistory } from "../components/ImportHistory";
import { api } from "../lib/api";

export function ImportActivity() {
  const importsQ = useQuery({ queryKey: ["imports"], queryFn: api.getImports });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Clock3 size={18} className="text-aurora-cyan" />
            <h1 className="text-2xl font-semibold text-white">Import history</h1>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Snapshot lineage and matching health. New data is added from Data.
          </p>
        </div>
        <span className="chip chip-muted tabular">
          {importsQ.data?.length ?? 0} snapshots
        </span>
      </div>
      <ImportHistory imports={importsQ.data ?? []} />
    </div>
  );
}
