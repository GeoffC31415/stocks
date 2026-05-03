import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDownUp, Loader2 } from "lucide-react";
import { api, formatSnapshotDateIso, type SnapshotDiffRow } from "../lib/api";
import { pct, toGbp } from "../lib/formatters";

type SortKey = "value" | "weight" | "quantity" | "name";

const numberOrZero = (value: number | null | undefined) => value ?? 0;

export function Diff() {
  const [params, setParams] = useSearchParams();
  const [sort, setSort] = useState<SortKey>("value");

  const importsQ = useQuery({ queryKey: ["imports"], queryFn: api.getImports });
  const imports = importsQ.data ?? [];
  const latest = imports[0];
  const previous = imports[1];

  const fromBatchId = Number(params.get("from") ?? previous?.id ?? 0);
  const toBatchId = Number(params.get("to") ?? latest?.id ?? 0);

  const diffQ = useQuery({
    queryKey: ["imports-diff", fromBatchId, toBatchId],
    queryFn: () => api.compareImports(fromBatchId, toBatchId),
    enabled: fromBatchId > 0 && toBatchId > 0,
  });

  const rows = useMemo(() => {
    const data = diffQ.data?.rows ?? [];
    return [...data].sort((a, b) => {
      if (sort === "name") return a.security_name.localeCompare(b.security_name);
      if (sort === "quantity") {
        return Math.abs(numberOrZero(b.delta_quantity)) - Math.abs(numberOrZero(a.delta_quantity));
      }
      if (sort === "weight") {
        return Math.abs(numberOrZero(b.delta_weight_pct)) - Math.abs(numberOrZero(a.delta_weight_pct));
      }
      return Math.abs(numberOrZero(b.delta_value_gbp)) - Math.abs(numberOrZero(a.delta_value_gbp));
    });
  }, [diffQ.data?.rows, sort]);

  const setBatch = (key: "from" | "to", value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white" style={{ letterSpacing: "-0.02em" }}>
            Snapshot diff
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Compare quantities, values, prices and portfolio weights between two imports.
          </p>
        </div>
        <Link to="/import" className="chip chip-muted">
          Import history
        </Link>
      </div>

      <div className="glass flex flex-wrap items-center gap-3 rounded-2xl p-4">
        <select
          value={fromBatchId || ""}
          onChange={(event) => setBatch("from", event.target.value)}
          className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
        >
          {imports.map((batch) => (
            <option key={batch.id} value={batch.id}>
              From {formatSnapshotDateIso(batch.as_of_date)} #{batch.id}
            </option>
          ))}
        </select>
        <ArrowDownUp size={14} className="text-slate-500" />
        <select
          value={toBatchId || ""}
          onChange={(event) => setBatch("to", event.target.value)}
          className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
        >
          {imports.map((batch) => (
            <option key={batch.id} value={batch.id}>
              To {formatSnapshotDateIso(batch.as_of_date)} #{batch.id}
            </option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as SortKey)}
          className="ml-auto rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-200 focus:border-aurora-cyan/60 focus:outline-none"
        >
          <option value="value">Sort: value delta</option>
          <option value="weight">Sort: weight delta</option>
          <option value="quantity">Sort: quantity delta</option>
          <option value="name">Sort: name</option>
        </select>
      </div>

      <div className="glass overflow-hidden rounded-2xl">
        {importsQ.isLoading || diffQ.isLoading ? (
          <div className="flex h-56 items-center justify-center text-sm text-slate-500">
            <Loader2 size={18} className="mr-2 animate-spin" />
            Loading diff...
          </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            Choose two imports to compare.
          </div>
        ) : (
          <div className="max-h-[640px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-aurora-base/85 backdrop-blur-md">
                <tr className="text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  <th className="px-4 py-3">Instrument</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Qty</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">Price</th>
                  <th className="px-4 py-3 text-right">Weight</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <DiffTableRow key={row.instrument_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function signed(value: number | null, formatter: (value: number) => string) {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${formatter(value)}`;
}

function DiffTableRow({ row }: { row: SnapshotDiffRow }) {
  const isPositive = numberOrZero(row.delta_value_gbp) >= 0;
  return (
    <tr className="border-t border-white/[0.04] hover:bg-white/[0.03]">
      <td className="px-4 py-2.5">
        <div className="font-medium text-white">{row.identifier}</div>
        <div className="truncate text-xs text-slate-500">{row.security_name}</div>
      </td>
      <td className="px-4 py-2.5">
        <span className="chip chip-muted capitalize">{row.status}</span>
      </td>
      <td className="tabular px-4 py-2.5 text-right text-slate-300">
        {signed(row.delta_quantity, (value) => value.toFixed(4))}
      </td>
      <td className={`tabular px-4 py-2.5 text-right font-medium ${isPositive ? "text-pos" : "text-neg"}`}>
        {signed(row.delta_value_gbp, toGbp)}
      </td>
      <td className="tabular px-4 py-2.5 text-right text-slate-300">
        {row.delta_price == null ? "—" : signed(row.delta_price, (value) => value.toFixed(2))}
      </td>
      <td className="tabular px-4 py-2.5 text-right text-slate-300">
        {row.delta_weight_pct == null ? "—" : signed(row.delta_weight_pct, pct)}
      </td>
    </tr>
  );
}
