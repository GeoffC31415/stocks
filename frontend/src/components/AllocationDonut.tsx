import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { AllocationCategory, AllocationDimension } from "../lib/api";
import { toGbp } from "../lib/formatters";

const PALETTE = [
  "#22d3ee",
  "#a78bfa",
  "#34d399",
  "#f472b6",
  "#60a5fa",
  "#fb7185",
  "#4ade80",
  "#e879f9",
];

/** Amber, distinct from the palette, so the Unclassified slice is explicit. */
const UNCLASSIFIED_FILL = "#f59e0b";

const dimensionLabel = (dimension: AllocationDimension): string =>
  ({ asset_class: "asset class", sector: "sector", region: "region", account: "account", currency: "source currency" })[dimension];

/**
 * Allocation donut: slice area is current GBP weight, the centre carries the
 * HHI concentration index, and the legend table stays fully readable with
 * the Unclassified bucket made explicit. Empty allocations render a plain
 * "No positions" state instead of a zero donut.
 */
export function AllocationDonut({
  categories,
  totalValue,
  hhi,
  dimension = "asset_class",
}: {
  categories: AllocationCategory[];
  totalValue: number;
  hhi: number;
  dimension?: AllocationDimension;
}) {
  if (categories.length === 0) {
    return (
      <p className="rounded-xl bg-white/[0.02] p-4 text-center text-xs text-slate-500">
        No positions
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative mx-auto h-52 w-52 sm:max-w-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={categories}
              dataKey="value"
              nameKey="label"
              innerRadius="68%"
              outerRadius="100%"
              paddingAngle={1}
              stroke="none"
              isAnimationActive={false}
            >
              {categories.map((category, index) => (
                <Cell
                  key={category.label}
                  fill={
                    category.label === "Unclassified"
                      ? UNCLASSIFIED_FILL
                      : PALETTE[index % PALETTE.length]
                  }
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span
            data-testid="allocation-donut-center"
            className="tabular text-2xl font-semibold text-white"
          >
            {Math.round(hhi)}
          </span>
        </div>
      </div>

      <div className="text-center">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          HHI
        </p>
        <p className="mt-1 text-[11px] text-slate-600">
          {toGbp(totalValue)} invested · lower HHI is more diversified
        </p>
      </div>

      <table aria-label={`By ${dimensionLabel(dimension)}`} className="w-full table-fixed break-words text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-slate-600">
            <th scope="col" className="pb-2 font-semibold">
              Class
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Weight
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Value
            </th>
            <th scope="col" className="pb-2 text-right font-semibold">
              Holdings
            </th>
          </tr>
        </thead>
        <tbody>
          {categories.map((category, index) => (
            <tr key={category.label} className="border-t border-white/[0.04]">
              <td
                className={
                  category.label === "Unclassified" ? "font-medium text-amber-200" : "text-slate-200"
                }
              >
                {category.label}
              {" "}</td>
              <td className="tabular text-slate-400">{category.weightPct.toFixed(1)}%{" "}</td>
              <td className="tabular text-slate-300">{toGbp(category.value)}{" "}</td>
              <td className="tabular text-slate-600">· {category.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
