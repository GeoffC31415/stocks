import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { ImportPanel } from "../components/ImportPanel";
import { ImportHistory } from "../components/ImportHistory";

export function ImportPage() {
  const importsQ = useQuery({
    queryKey: ["imports"],
    queryFn: api.getImports,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1
          className="text-2xl font-semibold text-white"
          style={{ letterSpacing: "-0.02em" }}
        >
          Import data
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload Barclays portfolio snapshots and order history.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <ImportPanel />
        </div>
        <div className="lg:col-span-2">
          <ImportHistory imports={importsQ.data ?? []} />
        </div>
      </div>
    </div>
  );
}
