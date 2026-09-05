import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers3, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type AllocationDimension } from "../lib/api";
import { AllocationDonut } from "./AllocationDonut";

import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";


const DIMENSIONS: { key: AllocationDimension; label: string }[] = [
  { key: "asset_class", label: "Asset class" },
  { key: "sector", label: "Sector" },
  { key: "region", label: "Region" },
  { key: "account", label: "Account" },
  { key: "currency", label: "Source currency" },
];

export function AllocationAnalysisPanel() {
  const { accountFilter } = usePreferences();
  const [dimension, setDimension] = useState<AllocationDimension>("asset_class");
  const accountName = accountFilter === "all" ? null : accountFilter;
  const allocationQ = useQuery({
    queryKey: ["allocation", dimension, accountName],
    queryFn: () => api.getAllocation(dimension, accountName),
  });
  const analysis = allocationQ.data;
  if (allocationQ.isError) return <div role="alert" className="space-y-3 rounded-xl border border-red-400/20 p-4 text-sm text-slate-300">
    <p>Unable to load allocation. No allocation estimates are shown.</p>
    <button type="button" className="min-h-11 rounded-lg border border-white/20 px-4 focus-visible:outline" onClick={() => void allocationQ.refetch()}>Retry</button>
  </div>;
  if (!analysis) return <p role="status">Loading allocation…</p>;
  if (analysis.holdings.length === 0) return <section className="space-y-3 text-sm text-slate-300">
    <h1 className="text-2xl font-semibold">Allocation & concentration</h1>
    <p role="status">No eligible positions for the selected account.</p>
    <p>Cash excluded in all dimensions ({analysis.cash_policy}).</p>
    <p>{analysis.denominator_description}</p>
  </section>;
  const unclassified = analysis.categories.find((row) => row.label === "Unclassified");
  const dimensionLabel =
    DIMENSIONS.find((item) => item.key === dimension)!.label.toLowerCase();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Layers3 size={18} className="text-aurora-cyan" />
            <h1 className="text-2xl font-semibold text-white">Allocation & concentration</h1>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Position concentration and classification exposure for the selected account.
          </p>
        </div>
        <div role="group" aria-label="Allocation dimension" className="flex flex-wrap gap-1 rounded-lg border border-white/10 p-1">
          {DIMENSIONS.map((item) => <button key={item.key} type="button" aria-pressed={dimension === item.key}
            onClick={() => setDimension(item.key)}
            className={`min-h-11 rounded-md px-3 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300 ${dimension === item.key ? "bg-violet-600 text-white" : "text-slate-300 hover:bg-white/10"}`}>
            {item.label}
          </button>)}
        </div>
      </div>

      <section aria-label="Allocation methodology" className="space-y-1 text-xs text-slate-400">
        <p>Cash excluded in all dimensions ({analysis.cash_policy}).</p>
        <p>{analysis.denominator_description}</p>
        {dimension === "currency" && <p>Source currency of the holding, not underlying FX exposure.</p>}
        <h2 className="font-semibold text-slate-200">Classification completion</h2>
        <p>{analysis.classification.classified_count} of {analysis.classification.holding_count} holdings ({analysis.classification.classified_count_pct.toFixed(1)}%) classified.</p>
        <p>{toGbp(analysis.classification.classified_value_gbp)} of {toGbp(analysis.classification.total_value_gbp)} ({analysis.classification.classified_value_pct.toFixed(1)}%) of GBP value classified.</p>
      </section>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Invested value" value={toGbp(analysis.totalValue)} />
        <Metric label="Largest holding" value={`${analysis.top1Pct.toFixed(1)}%`} />
        <Metric label="Top five" value={`${analysis.top5Pct.toFixed(1)}%`} />
        <Metric
          label="Concentration index"
          value={analysis.hhi.toFixed(0)}
          note="HHI of position weights; does not measure fund overlap or correlation"
        />
      </div>

      {unclassified && unclassified.weightPct > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.05] px-4 py-3">
          <ShieldAlert size={16} className="text-amber-300" />
          <p className="text-xs text-slate-300">
            {unclassified.count} holding{unclassified.count === 1 ? " is" : "s are"} unclassified ({unclassified.weightPct.toFixed(1)}% of value).
          </p>
          <Link to="/data?tab=classifications" className="ml-auto text-xs font-medium text-amber-200 hover:text-amber-100">
            Complete classifications
          </Link>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="glass min-w-0 rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">By {dimensionLabel}</h2>
          <div className="mt-4">
            <AllocationDonut
              categories={analysis.categories}
              totalValue={analysis.totalValue}
              dimension={dimension}
            />
          </div>
        </section>

        <section className="glass min-w-0 rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">Largest holdings</h2>
          <div className="mt-3 space-y-2">
            {analysis.holdings.slice(0, 10).map((row, index) => (
              <div key={row.id} className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3 py-2">
                <span className="tabular w-5 text-[10px] text-slate-600">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-slate-200">{row.identifier}</p>
                  <p className="truncate text-[10px] text-slate-600">{row.label}</p>
                </div>
                <div className="tabular text-right text-xs text-slate-300">
                  <p>{row.weightPct.toFixed(1)}%</p>
                  <p className="text-[10px] text-slate-600">{toGbp(row.value)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className="tabular mt-1 text-xl font-semibold text-white">{value}</p>
      {note ? <p className="mt-1 text-[10px] text-slate-600">{note}</p> : null}
    </div>
  );
}
