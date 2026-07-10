import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers3, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import {
  calculateAllocation,
  type AllocationDimension,
} from "../lib/allocationAnalysis";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { SegmentedControl, type Segment } from "./SegmentedControl";

const DIMENSIONS: Segment<AllocationDimension>[] = [
  { key: "asset_class", label: "Asset class" },
  { key: "sector", label: "Sector" },
  { key: "region", label: "Region" },
];

export function AllocationAnalysisPanel() {
  const { accountFilter } = usePreferences();
  const [dimension, setDimension] = useState<AllocationDimension>("asset_class");
  const instrumentsQ = useQuery({ queryKey: ["instruments"], queryFn: api.getInstruments });
  const instruments = useMemo(
    () =>
      accountFilter === "all"
        ? (instrumentsQ.data ?? [])
        : (instrumentsQ.data ?? []).filter(
            (instrument) => instrument.account_name === accountFilter,
          ),
    [accountFilter, instrumentsQ.data],
  );
  const analysis = useMemo(
    () => calculateAllocation(instruments, dimension),
    [dimension, instruments],
  );
  const unclassified = analysis.categories.find((row) => row.label === "Unclassified");

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
        <SegmentedControl
          layoutId="allocation-dimension"
          value={dimension}
          onChange={setDimension}
          segments={DIMENSIONS}
          tone="violet"
          size="sm"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Invested value" value={toGbp(analysis.totalValue)} />
        <Metric label="Largest holding" value={`${analysis.top1Pct.toFixed(1)}%`} />
        <Metric label="Top five" value={`${analysis.top5Pct.toFixed(1)}%`} />
        <Metric
          label="Concentration index"
          value={analysis.hhi.toFixed(0)}
          note="HHI: lower is more diversified"
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
        <section className="glass rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-white">By {DIMENSIONS.find((item) => item.key === dimension)?.label.toLowerCase()}</h2>
          <div className="mt-4 space-y-3">
            {analysis.categories.map((row) => (
              <div key={row.label}>
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className={row.label === "Unclassified" ? "text-amber-200" : "text-slate-200"}>
                    {row.label} <span className="text-slate-600">· {row.count}</span>
                  </span>
                  <span className="tabular text-slate-400">{row.weightPct.toFixed(1)}% · {toGbp(row.value)}</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className={row.label === "Unclassified" ? "h-full rounded-full bg-amber-400" : "h-full rounded-full bg-aurora-accent"}
                    style={{ width: `${Math.min(row.weightPct, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="glass rounded-2xl p-5">
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
