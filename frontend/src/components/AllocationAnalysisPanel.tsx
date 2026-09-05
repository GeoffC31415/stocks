import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers3, ShieldAlert } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { holdingsLink } from "../lib/investigationLinks";
import { api, type AllocationDimension, type AllocationGrouping } from "../lib/api";
import { AllocationDonut } from "./AllocationDonut";
import { MetricInfo } from "./MetricInfo";
import { TargetDriftPanel } from "./TargetDriftPanel";
import { AllocationScenarioPanel } from "./AllocationScenarioPanel";

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
  const {search}=useLocation();
  const [dimension, setDimension] = useState<AllocationDimension>("asset_class");
  const [groupBy, setGroupBy] = useState<AllocationGrouping>("security");
  const accountName = accountFilter === "all" ? null : accountFilter;
  const allocationQ = useQuery({
    queryKey: ["allocation", dimension, accountName, groupBy],
    queryFn: () => api.getAllocation(dimension, accountName, groupBy),
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
          <p className="mt-1 text-sm text-slate-400">
            Security or account-position concentration in the selected scope.
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

      <div role="group" aria-label="Exposure grouping" className="flex flex-wrap gap-2">
        {(["security", "position"] as const).map((mode) => <button type="button" key={mode}
          aria-pressed={groupBy === mode} onClick={() => setGroupBy(mode)}
          className="min-h-11 rounded-lg border border-white/20 px-3 text-sm focus-visible:outline">
          {mode === "security" ? "Security exposure" : "Account positions"}
        </button>)}
      </div>
      <section aria-label="Allocation methodology" className="space-y-1 text-xs text-slate-400">
        <p>Security exposure combines only reviewed source-identifier/listing mappings with the same source currency. Unverified or conflicting identities stay separate; names and editable tickers alone never merge positions.</p>
        <p>Cash excluded in all dimensions ({analysis.cash_policy}).</p>
        <p>{analysis.denominator_description}</p>
        {dimension === "currency" && <p>Source currency of the holding, not underlying FX exposure.</p>}
        <h2 className="font-semibold text-slate-200">Classification completion</h2>
        <p>{analysis.classification.classified_count} of {analysis.classification.holding_count} holdings ({analysis.classification.classified_count_pct.toFixed(1)}%) classified.</p>
        <p>{toGbp(analysis.classification.classified_value_gbp)} of {toGbp(analysis.classification.total_value_gbp)} ({analysis.classification.classified_value_pct.toFixed(1)}%) of GBP value classified.</p>
      </section>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Invested value" value={toGbp(analysis.totalValue)} />
        <Metric label={groupBy === "security" ? "Largest security exposure" : "Largest position"} value={`${analysis.top1Pct.toFixed(1)}%`} />
        <Metric label="Top five" value={`${analysis.top5Pct.toFixed(1)}%`} />
        <Metric
          label="Concentration index"
          value={analysis.hhi.toFixed(0)}
          note={`HHI of ${groupBy} weights; not proof of diversification. Does not measure fund overlap or correlation.`}
        />
      </div>

      <MetricInfo label="concentration index" topic="hhi" context={`Current ${groupBy}-weight concentration; cash excluded`} />

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
              categoryHref={label=>analysis.category_instruments?.[label]?.length?holdingsLink(search,{account:accountName??"all",instrumentIds:analysis.category_instruments[label],category:{dimension,label}}):undefined}
            />
          </div>
        </section>

        <section className="glass min-w-0 rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">{groupBy === "security" ? "Largest security exposures" : "Largest account positions"}</h2>
          <div className="mt-3 space-y-2">
            {analysis.holdings.slice(0, 10).map((row, index) => (
              <div key={row.id} className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3 py-2">
                <span className="tabular w-5 text-xs text-slate-400">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-slate-200">{row.identifier}</p>
                  <p className="truncate text-xs text-slate-400">{row.label}</p>
                  <details className="mt-2 break-words text-xs text-slate-300">
                    <summary className="cursor-pointer py-2">Accounts and positions ({row.constituents.length})</summary>
                    <p>{row.aggregation_confidence === "verified_listing" ? "Reviewed identifier/listing match" : "Identity unverified — separate position"}</p>
                    {row.aggregation_reasons.map((reason) => <p key={reason}>{reason}</p>)}
                    {row.constituents.map((position) => <p key={position.id}>
                      {position.account_name} · {position.identifier} · ID {position.id} · {toGbp(position.value)} · {position.source_currency ?? "Unknown currency"}
                    </p>)}
                  </details>
                </div>
                <div className="tabular text-right text-xs text-slate-300">
                  <p>{row.weightPct.toFixed(1)}%</p>
                  <p className="text-xs text-slate-400">{toGbp(row.value)}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      <TargetDriftPanel />
      <AllocationScenarioPanel />
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className="tabular mt-1 text-xl font-semibold text-white">{value}</p>
      {note ? <p className="mt-1 text-xs text-slate-400">{note}</p> : null}
    </div>
  );
}
