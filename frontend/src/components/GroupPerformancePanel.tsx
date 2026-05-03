import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Layers, Sparkles, X } from "lucide-react";
import type { GroupPerformance, GroupPerformanceMember } from "../lib/api";
import { Sparkline } from "./Sparkline";
import { TrendChip } from "./TrendChip";
import { SegmentedControl, type Segment } from "./SegmentedControl";
import { toGbp } from "../lib/formatters";
import {
  chartUtcMs,
  formatChartDayTick,
  formatChartTooltipDay,
} from "../lib/chartDates";

const GROUP_PALETTE = [
  "#22d3ee",
  "#a78bfa",
  "#34d399",
  "#fbbf24",
  "#f472b6",
  "#60a5fa",
  "#fb923c",
  "#f87171",
];

type SortKey = "value" | "pnl" | "cagr";
type ChartMode = "value" | "rebased";

const SORT_LABELS: Record<SortKey, string> = {
  value: "Value",
  pnl: "P&L",
  cagr: "CAGR",
};

const formatPctSigned = (v: number | null | undefined): string => {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
};

const groupColor = (group: GroupPerformance, idx: number): string =>
  group.color || GROUP_PALETTE[idx % GROUP_PALETTE.length];

export function GroupPerformancePanel({
  groups,
  isLoading,
}: {
  groups: GroupPerformance[];
  isLoading: boolean;
}) {
  const [sort, setSort] = useState<SortKey>("value");
  const [chartMode, setChartMode] = useState<ChartMode>("rebased");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const ranked = useMemo(() => {
    const populated = groups.filter((g) => g.member_count > 0);
    return [...populated].sort((a, b) => {
      if (sort === "pnl") return b.total_pnl_gbp - a.total_pnl_gbp;
      if (sort === "cagr") {
        const ca = a.weighted_cagr_pct ?? a.combined_cagr_pct ?? -Infinity;
        const cb = b.weighted_cagr_pct ?? b.combined_cagr_pct ?? -Infinity;
        return cb - ca;
      }
      return b.total_current_value_gbp - a.total_current_value_gbp;
    });
  }, [groups, sort]);

  const colorFor = useMemo(() => {
    const map = new Map<number, string>();
    ranked.forEach((g, idx) => map.set(g.group_id, groupColor(g, idx)));
    return map;
  }, [ranked]);

  const totals = useMemo(() => {
    let value = 0;
    let cost = 0;
    for (const g of ranked) {
      value += g.total_current_value_gbp;
      cost += g.total_net_cost_gbp;
    }
    const pnl = value - cost;
    const pnlPct = cost > 0 ? (pnl / cost) * 100 : null;
    return { value, cost, pnl, pnlPct };
  }, [ranked]);

  const chartData = useMemo(() => {
    if (ranked.length === 0) return [];
    const dateSet = new Set<string>();
    for (const g of ranked) {
      for (const p of g.timeseries) dateSet.add(p.as_of_date);
    }
    const dates = [...dateSet].sort();
    return dates.map((date) => {
      const row: Record<string, number | string | null> = {
        as_of_date: date,
        chartTime: chartUtcMs(date),
      };
      for (const g of ranked) {
        const point = g.timeseries.find((p) => p.as_of_date === date);
        if (chartMode === "value") {
          row[`g_${g.group_id}`] = point?.value_gbp ?? null;
        } else {
          const first = g.timeseries.find((p) => p.value_gbp > 0);
          if (!first || !point || point.value_gbp <= 0) {
            row[`g_${g.group_id}`] = null;
          } else {
            row[`g_${g.group_id}`] = (point.value_gbp / first.value_gbp) * 100;
          }
        }
      }
      return row;
    });
  }, [ranked, chartMode]);

  const selectedGroup = useMemo(
    () => ranked.find((g) => g.group_id === selectedId) ?? null,
    [ranked, selectedId],
  );

  if (isLoading) {
    return (
      <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
        <Sparkles className="mx-auto animate-pulse text-aurora-cyan" size={28} />
        <p className="mt-3 text-sm text-slate-400">
          Loading group performance…
        </p>
      </div>
    );
  }

  if (ranked.length === 0) {
    return (
      <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
        <Layers className="mx-auto text-slate-500" size={28} />
        <h2 className="mt-3 text-lg font-semibold text-white">
          No populated groups yet
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Head to the Groups tab and add instruments to a group to see combined
          performance here.
        </p>
      </div>
    );
  }

  const sortSegments: Segment<SortKey>[] = (
    Object.keys(SORT_LABELS) as SortKey[]
  ).map((k) => ({ key: k, label: SORT_LABELS[k] }));

  return (
    <div className="space-y-5">
      {/* Portfolio-of-groups headline */}
      <div className="glass relative overflow-hidden rounded-2xl p-5">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 60% at 0% 0%, rgba(167,139,250,0.18), transparent 65%), radial-gradient(60% 60% at 100% 100%, rgba(34,211,238,0.16), transparent 65%)",
          }}
        />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Across {ranked.length} group{ranked.length === 1 ? "" : "s"}
            </p>
            <p
              className="tabular mt-1 text-3xl font-semibold text-white"
              style={{ letterSpacing: "-0.02em" }}
            >
              {toGbp(totals.value)}
            </p>
            <p className="tabular mt-1 text-xs text-slate-500">
              Net cost {toGbp(totals.cost)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`tabular text-2xl font-semibold ${
                totals.pnl >= 0 ? "text-pos" : "text-neg"
              }`}
            >
              {totals.pnl >= 0 ? "+" : ""}
              {toGbp(totals.pnl)}
            </span>
            <TrendChip value={totals.pnlPct} suffix="%" />
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          layoutId="group-perf-sort"
          value={sort}
          onChange={setSort}
          tone="violet"
          size="sm"
          segments={sortSegments}
        />
        <p className="text-[11px] text-slate-500">
          Click a card for the member breakdown.
        </p>
      </div>

      {/* Group cards */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {ranked.map((g) => {
          const color = colorFor.get(g.group_id) || "#22d3ee";
          const isSelected = selectedId === g.group_id;
          const cagr = g.weighted_cagr_pct ?? g.combined_cagr_pct;
          const tone = g.total_pnl_gbp >= 0 ? "pos" : "neg";
          const sparkData = g.timeseries.map((p) => ({
            value: p.value_gbp,
          }));
          return (
            <motion.button
              key={g.group_id}
              type="button"
              whileHover={{ y: -2 }}
              transition={{ type: "spring", stiffness: 260, damping: 24 }}
              onClick={() =>
                setSelectedId((prev) =>
                  prev === g.group_id ? null : g.group_id,
                )
              }
              data-active={isSelected || undefined}
              className="glass glass-hover gradient-border relative overflow-hidden rounded-2xl p-5 text-left"
            >
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0"
                style={{
                  background: `radial-gradient(80% 80% at 100% 0%, ${color}22, transparent 65%)`,
                }}
              />
              <div className="relative">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{
                      background: color,
                      boxShadow: `0 0 12px ${color}80`,
                    }}
                  />
                  <h3 className="truncate text-sm font-semibold text-white">
                    {g.name}
                  </h3>
                  <span className="tabular ml-auto rounded-full bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-400">
                    {g.member_count}{" "}
                    {g.member_count === 1 ? "holding" : "holdings"}
                  </span>
                </div>

                <div className="mt-4 flex items-baseline justify-between gap-3">
                  <p
                    className="tabular text-2xl font-semibold text-white"
                    style={{ letterSpacing: "-0.01em" }}
                  >
                    {toGbp(g.total_current_value_gbp)}
                  </p>
                  <TrendChip value={cagr} format={(v) => `${formatPctSigned(v)} /yr`} />
                </div>

                <div className="mt-1.5 flex items-center justify-between text-xs">
                  <span className="text-slate-500">
                    Cost {toGbp(g.total_net_cost_gbp)}
                  </span>
                  <span
                    className={`tabular font-semibold ${
                      g.total_pnl_gbp >= 0 ? "text-pos" : "text-neg"
                    }`}
                  >
                    {g.total_pnl_gbp >= 0 ? "+" : ""}
                    {toGbp(g.total_pnl_gbp)}{" "}
                    <span className="text-slate-500 font-normal">
                      ({formatPctSigned(g.pnl_pct)})
                    </span>
                  </span>
                </div>

                <div className="mt-3 -mx-1">
                  <Sparkline
                    data={sparkData}
                    dataKey="value"
                    tone={tone}
                    height={44}
                  />
                </div>

                {g.earliest_order_date && (
                  <p className="mt-2 text-[10px] uppercase tracking-[0.14em] text-slate-600">
                    Held since {g.earliest_order_date.slice(0, 7)}
                  </p>
                )}
              </div>
            </motion.button>
          );
        })}
      </div>

      {/* Comparison chart */}
      {chartData.length > 1 && (
        <div className="glass relative overflow-hidden rounded-2xl p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">
                {chartMode === "rebased"
                  ? "Group performance, rebased"
                  : "Group value over time"}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                {chartMode === "rebased"
                  ? "Each group rebased to 100 at first snapshot — the line that climbs fastest is winning."
                  : "Combined value of each group at every imported snapshot."}
              </p>
            </div>
            <SegmentedControl
              layoutId="group-perf-chart"
              value={chartMode}
              onChange={setChartMode}
              tone="accent"
              size="sm"
              segments={[
                { key: "rebased", label: "Rebased" },
                { key: "value", label: "Value £" },
              ]}
            />
          </div>

          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(148,163,184,0.08)"
                />
                <XAxis
                  dataKey="chartTime"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickFormatter={formatChartDayTick}
                  minTickGap={32}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) =>
                    chartMode === "rebased"
                      ? `${Number(v).toFixed(0)}`
                      : `£${(Number(v) / 1000).toFixed(0)}k`
                  }
                />
                <Tooltip
                  content={
                    <RebasedTooltip
                      groups={ranked}
                      colorFor={colorFor}
                      mode={chartMode}
                    />
                  }
                  cursor={{
                    stroke: "rgba(255,255,255,0.18)",
                    strokeDasharray: 3,
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
                  iconType="circle"
                />
                {ranked.map((g) => (
                  <Line
                    key={g.group_id}
                    type="monotone"
                    dataKey={`g_${g.group_id}`}
                    stroke={colorFor.get(g.group_id)}
                    strokeWidth={2}
                    name={g.name}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Detail */}
      <AnimatePresence>
        {selectedGroup && (
          <motion.div
            key={selectedGroup.group_id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.18 }}
          >
            <GroupDetailCard
              group={selectedGroup}
              color={colorFor.get(selectedGroup.group_id) || "#22d3ee"}
              onClose={() => setSelectedId(null)}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RebasedTooltip({
  active,
  payload,
  label,
  groups,
  colorFor,
  mode,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | null; dataKey?: string }>;
  label?: string | number;
  groups: GroupPerformance[];
  colorFor: Map<number, string>;
  mode: ChartMode;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const headline =
    typeof label === "number"
      ? formatChartTooltipDay(label)
      : String(label ?? "");
  const rows = payload
    .filter((p) => p.value != null)
    .map((p) => {
      const id = Number((p.dataKey ?? "").replace("g_", ""));
      const g = groups.find((x) => x.group_id === id);
      if (!g) return null;
      return { id, name: g.name, value: p.value as number };
    })
    .filter((r): r is { id: number; name: string; value: number } => r !== null)
    .sort((a, b) => b.value - a.value);

  return (
    <div className="rounded-xl border border-white/[0.08] bg-aurora-base/95 px-3 py-2 text-xs shadow-glass backdrop-blur-md">
      <p className="font-semibold text-slate-300">{headline}</p>
      <div className="mt-1.5 space-y-1">
        {rows.map((r) => (
          <div key={r.id} className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: colorFor.get(r.id) }}
            />
            <span className="text-slate-400">{r.name}</span>
            <span className="tabular ml-auto font-semibold text-white">
              {mode === "rebased" ? r.value.toFixed(1) : toGbp(r.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function GroupDetailCard({
  group,
  color,
  onClose,
}: {
  group: GroupPerformance;
  color: string;
  onClose: () => void;
}) {
  const sortedMembers: GroupPerformanceMember[] = useMemo(
    () =>
      [...group.members].sort(
        (a, b) => (b.current_value_gbp ?? 0) - (a.current_value_gbp ?? 0),
      ),
    [group.members],
  );

  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(70% 60% at 0% 0%, ${color}1f, transparent 65%)`,
        }}
      />
      <div className="relative">
        <div className="flex items-center gap-2">
          <span
            className="h-3 w-3 rounded-full"
            style={{ background: color, boxShadow: `0 0 14px ${color}80` }}
          />
          <h3 className="text-sm font-semibold text-white">{group.name}</h3>
          <span className="ml-2 text-xs text-slate-500">
            {group.member_count}{" "}
            {group.member_count === 1 ? "holding" : "holdings"} ·{" "}
            {group.members_with_value} active
          </span>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-md p-1 text-slate-500 hover:bg-white/[0.06] hover:text-slate-200"
            aria-label="Close detail"
          >
            <X size={14} />
          </button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <DetailKpi
            label="Current value"
            value={toGbp(group.total_current_value_gbp)}
          />
          <DetailKpi
            label="Net cost"
            value={toGbp(group.total_net_cost_gbp)}
          />
          <DetailKpi
            label="P&L"
            value={`${group.total_pnl_gbp >= 0 ? "+" : ""}${toGbp(group.total_pnl_gbp)}`}
            sub={formatPctSigned(group.pnl_pct)}
            tone={group.total_pnl_gbp >= 0 ? "pos" : "neg"}
          />
          <DetailKpi
            label="CAGR"
            value={
              group.weighted_cagr_pct != null
                ? `${formatPctSigned(group.weighted_cagr_pct)} /yr`
                : "—"
            }
            sub={
              group.combined_cagr_pct != null
                ? `Combined ${formatPctSigned(group.combined_cagr_pct)} /yr`
                : undefined
            }
            tone={
              (group.weighted_cagr_pct ?? 0) >= 0 ? "pos" : "neg"
            }
          />
        </div>

        <div className="mt-5 overflow-hidden rounded-xl border border-white/[0.04]">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-left text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              <tr>
                <th className="px-4 py-3">Holding</th>
                <th className="px-4 py-3 text-right">Value</th>
                <th className="px-4 py-3 text-right">Weight</th>
                <th className="px-4 py-3 text-right">Net cost</th>
                <th className="px-4 py-3 text-right">P&amp;L</th>
                <th className="px-4 py-3 text-right">CAGR</th>
              </tr>
            </thead>
            <tbody>
              {sortedMembers.map((m, idx) => {
                const pnl = m.pnl_gbp;
                const isPos = (pnl ?? 0) >= 0;
                const dash = <span className="text-slate-700">—</span>;
                return (
                  <tr
                    key={m.instrument_id}
                    className={`border-t border-white/[0.04] ${
                      idx % 2 === 0 ? "bg-white/[0.012]" : ""
                    } hover:bg-white/[0.04]`}
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-white">
                        {m.identifier}
                      </div>
                      <div className="truncate text-xs text-slate-500">
                        {m.security_name}
                      </div>
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-slate-200">
                      {m.current_value_gbp != null
                        ? toGbp(m.current_value_gbp)
                        : dash}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <WeightBar value={m.weight_pct} color={color} />
                    </td>
                    <td className="tabular px-4 py-2.5 text-right text-slate-300">
                      {toGbp(m.net_cost_gbp)}
                    </td>
                    <td
                      className={`tabular px-4 py-2.5 text-right font-semibold ${
                        isPos ? "text-pos" : "text-neg"
                      }`}
                    >
                      {pnl != null
                        ? `${pnl >= 0 ? "+" : ""}${toGbp(pnl)}`
                        : dash}
                    </td>
                    <td
                      className={`tabular px-4 py-2.5 text-right ${
                        m.annualised_return_pct != null
                          ? (m.annualised_return_pct ?? 0) >= 0
                            ? "text-pos"
                            : "text-neg"
                          : ""
                      }`}
                    >
                      {m.annualised_return_pct != null
                        ? `${formatPctSigned(m.annualised_return_pct)} /yr`
                        : dash}
                    </td>
                  </tr>
                );
              })}
              {sortedMembers.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-6 text-center text-xs text-slate-500"
                  >
                    No members in this group.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function DetailKpi({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "pos" | "neg" | "default";
}) {
  const valueClass =
    tone === "pos" ? "text-pos" : tone === "neg" ? "text-neg" : "text-white";
  return (
    <div className="rounded-xl border border-white/[0.04] bg-white/[0.02] p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {label}
      </p>
      <p className={`tabular mt-1 text-lg font-semibold ${valueClass}`}>
        {value}
      </p>
      {sub && <p className="tabular mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function WeightBar({
  value,
  color,
}: {
  value: number | null;
  color: string;
}) {
  if (value == null) return <span className="text-slate-700">—</span>;
  const width = Math.min(100, Math.max(0, value));
  return (
    <div className="ml-auto flex w-32 items-center gap-2">
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${width}%`,
            background: color,
            boxShadow: `0 0 8px ${color}66`,
          }}
        />
      </div>
      <span className="tabular w-10 text-right text-xs text-slate-400">
        {value.toFixed(0)}%
      </span>
    </div>
  );
}
