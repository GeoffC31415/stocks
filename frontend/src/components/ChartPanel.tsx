import { useMemo, useState } from "react";
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
import type { CashflowPoint, EstimatedTimeseriesPoint } from "../lib/api";
import { toGbp } from "../lib/formatters";

type TimeseriesPoint = {
  as_of_date: string;
  total_value_gbp: number;
  total_book_cost_gbp: number;
};

type ChartTab = "estimated" | "deployment" | "value";

const TABS: { key: ChartTab; label: string }[] = [
  { key: "estimated", label: "Historical estimate" },
  { key: "deployment", label: "Capital deployment" },
  { key: "value", label: "Snapshot history" },
];

const kFormatter = (v: number) => `£${(v / 1000).toFixed(0)}k`;

export function ChartPanel({
  cashflow,
  timeseries,
  estimatedTimeseries,
  hasOrders,
}: {
  cashflow: CashflowPoint[];
  timeseries: TimeseriesPoint[];
  estimatedTimeseries: EstimatedTimeseriesPoint[];
  hasOrders: boolean;
}) {
  const [tab, setTab] = useState<ChartTab>("estimated");

  const mergedEstimated = useMemo(() => {
    const byMonth = new Map(cashflow.map((c) => [c.month, c]));
    return estimatedTimeseries.map((e) => ({
      month: e.month,
      estimated_value_gbp: e.estimated_value_gbp,
      cumulative_net_deployed:
        byMonth.get(e.month)?.cumulative_net_deployed ?? null,
    }));
  }, [cashflow, estimatedTimeseries]);

  const activeTab = hasOrders ? tab : "value";

  return (
    <div className="glass rounded-2xl p-5">
      {hasOrders && (
        <div className="mb-4 flex gap-1 rounded-lg border border-slate-700 bg-slate-900/60 p-1 w-fit">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === t.key
                  ? "bg-cyan-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {activeTab === "estimated" && (
        <>
          <h2 className="text-base font-semibold text-white">
            Portfolio value — historical estimate
          </h2>
          <p className="mb-3 mt-1 text-xs text-slate-500">
            Order-derived quantities × current prices. The gap above the
            deployed line is unrealised gain.
          </p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mergedEstimated}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="month" stroke="#94a3b8" tick={{ fontSize: 10 }} interval={11} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} tickFormatter={kFormatter} />
                <Tooltip formatter={(v) => toGbp(v as number)} labelFormatter={(l) => `Month: ${l}`} />
                <Legend />
                <Line type="monotone" dataKey="estimated_value_gbp" stroke="#22d3ee" name="Est. value (current prices)" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="cumulative_net_deployed" stroke="#a78bfa" name="Net cash deployed" dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {activeTab === "deployment" && (
        <>
          <h2 className="text-base font-semibold text-white">
            Capital deployment history
          </h2>
          <p className="mb-3 mt-1 text-xs text-slate-500">
            Cumulative net cash invested (discretionary buys − sell proceeds) and
            DRIP reinvested over time.
          </p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cashflow}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="month" stroke="#94a3b8" tick={{ fontSize: 10 }} interval={11} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} tickFormatter={kFormatter} />
                <Tooltip formatter={(v, name) => [toGbp(v as number), name]} labelFormatter={(l) => `Month: ${l}`} />
                <Legend />
                <Line type="monotone" dataKey="cumulative_net_deployed" stroke="#22d3ee" name="Net deployed" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="cumulative_drip" stroke="#f59e0b" name="DRIP cumulative" dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="cumulative_sells" stroke="#f43f5e" name="Cumulative sells" dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {activeTab === "value" && (
        <>
          <h2 className="text-base font-semibold text-white">
            Portfolio value — snapshot history
          </h2>
          <p className="mb-3 mt-1 text-xs text-slate-500">
            Actual values from each imported portfolio snapshot.
          </p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeseries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="as_of_date" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} tickFormatter={kFormatter} />
                <Tooltip formatter={(v) => toGbp(v as number)} />
                <Legend />
                <Line type="monotone" dataKey="total_value_gbp" stroke="#22d3ee" name="Value" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="total_book_cost_gbp" stroke="#a78bfa" name="Book cost" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
