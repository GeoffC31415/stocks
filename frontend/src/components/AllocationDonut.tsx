import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { AllocationCategory, AllocationDimension } from "../lib/api";
import { categoryColor } from "../lib/chartTheme";
import { compactGbp, toGbp, toGbpExact } from "../lib/formatters";

const headings: Record<AllocationDimension, string> = {
  asset_class: "Asset class", sector: "Sector", region: "Region", account: "Account", currency: "Source currency",
};

/** Category weights and exact GBP values remain available without colour or hover. */
export function AllocationDonut({ categories, totalValue, dimension = "asset_class" }: {
  categories: AllocationCategory[];
  totalValue: number;
  dimension?: AllocationDimension;
}) {
  const [exact, setExact] = useState(false);
  if (categories.length === 0) return <p className="p-4 text-center text-sm text-slate-400">No positions</p>;
  const currency = exact ? toGbpExact : toGbp;
  return <div className="space-y-4">
    <div className="relative mx-auto h-52 w-52 max-w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart><Pie data={categories} dataKey="value" nameKey="label" innerRadius="68%"
          outerRadius="100%" paddingAngle={1} stroke="none" isAnimationActive={false}>
          {categories.map((category) => <Cell key={category.label} fill={categoryColor(dimension, category.label)} />)}
        </Pie></PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span data-testid="allocation-donut-center" className="tabular text-2xl font-semibold text-slate-100">{compactGbp(totalValue)}</span>
        <span className="text-xs text-slate-400">Invested</span>
      </div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300">
      <span>{currency(totalValue)} invested · cash excluded</span>
      <button className="min-h-9 rounded-lg border border-slate-500/30 px-3 focus-visible:outline"
        type="button" aria-pressed={exact} onClick={() => setExact(!exact)}>{exact ? "Show rounded values" : "Show exact values"}</button>
    </div>
    <table aria-label={`By ${headings[dimension].toLowerCase()}`} className="w-full table-fixed break-words text-xs">
      <thead><tr className="text-left text-slate-300">
        <th scope="col" className="w-[36%] pb-2">{headings[dimension]}</th>
        <th scope="col" className="pb-2 text-right">Weight</th>
        <th scope="col" className="w-[28%] pb-2 text-right">Value</th>
        <th scope="col" className="pb-2 text-right">Holdings</th>
      </tr></thead>
      <tbody>{categories.map((category) => <tr key={category.label} className="border-t border-slate-500/20">
        <th scope="row" className={`py-2 text-left font-medium ${category.label === "Unclassified" ? "text-amber-200" : "text-slate-200"}`}>
          <span aria-hidden="true" className="mr-2 inline-block h-2 w-2 rounded-sm" style={{ background: categoryColor(dimension, category.label) }} />
          {category.label}
        </th>
        <td className="tabular py-2 text-right text-slate-300">{category.weightPct.toFixed(1)}%</td>
        <td className="tabular py-2 text-right text-slate-200">{currency(category.value)}</td>
        <td className="tabular py-2 text-right text-slate-400">{category.count}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}
