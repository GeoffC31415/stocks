import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info } from "lucide-react";
import type { Instrument, InstrumentHistoryPoint, Order } from "../lib/api";
import { chartUtcMs, formatChartDayTick, formatChartTooltipDay } from "../lib/chartDates";
import { compactGbp } from "../lib/formatters";
import { chartTheme } from "../lib/chartTheme";
import { ChartTooltip } from "./ChartTooltip";
import { OrderRow } from "./OrderRow";
import { Link } from "react-router-dom";
import { ordersLink } from "../lib/investigationLinks";
import { TimelineEvents } from "./TimelineEvents";

export function InstrumentDetail({
  name,
  instrument,
  trailingDripYieldPct,
  history,
  historyLoading,
  orders,
  ordersLoading,
  hasOrders,
  historyError = false, ordersError = false, onRetryHistory, onRetryOrders,
}: {
  name: string | null;
  instrument: Instrument | null;
  trailingDripYieldPct: number | null;
  history: InstrumentHistoryPoint[];
  historyLoading: boolean;
  orders: Order[];
  ordersLoading: boolean;
  hasOrders: boolean;
  historyError?: boolean; ordersError?: boolean; onRetryHistory?: () => void; onRetryOrders?: () => void;
}) {
  const [params, setParams] = useSearchParams();
  const showTimeline = params.get("events") === "on";
  const historyWithTime = useMemo(
    () =>
      history.map((h) => ({
        ...h,
        chartTime: chartUtcMs(h.as_of_date),
      })),
    [history],
  );


  return (
    <div className="glass flex h-full flex-col gap-4 rounded-2xl p-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Instrument detail
        </p>
        {name && (
          <h3 className="mt-1 truncate text-sm font-semibold text-white" title={name}>
            {name}
          </h3>
        )}
        {instrument ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="chip chip-muted">{instrument.identifier}</span>
            <span className="chip chip-muted">{instrument.account_name}</span>
            {instrument.ticker ? <span className="chip chip-muted">{instrument.ticker}</span> : null}
            {instrument.asset_class ? <span className="chip chip-muted">{instrument.asset_class}</span> : null}
            {instrument.sector ? <span className="chip chip-muted">{instrument.sector}</span> : null}
            {trailingDripYieldPct != null ? (
              <span className="chip chip-muted">
                Reinvestment proxy ratio {trailingDripYieldPct.toFixed(2)}%
              </span>
            ) : null}
            {instrument.latest_quote_as_of_date ? (
              <span className="chip chip-muted">
                Quote {instrument.latest_quote_as_of_date}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {instrument && <>
        <Link className="inline-flex min-h-11 items-center text-sm text-cyan-200 underline" to={ordersLink(params.toString(),{account:instrument.account_name,instrumentId:instrument.id})}>View matching orders</Link>
        <p className="text-xs text-slate-300">Reinvestment purchase proxy, not a dividend ledger. Trailing proxy yield unavailable: a same-window valuation denominator and transaction completeness are not validated.</p>
        <button type="button" className="min-h-9 text-left text-sm text-cyan-200 underline" aria-expanded={showTimeline} onClick={() => {
          const next = new URLSearchParams(params);
          if (showTimeline) next.delete("events"); else next.set("events", "on");
          setParams(next);
        }}>{showTimeline ? "Hide" : "Show"} instrument timeline</button>
        {showTimeline && <TimelineEvents instrumentId={instrument.id} />}
      </>}
      {historyLoading ? <p role="status">Loading history…</p> : historyError ? <div role="alert">History unavailable. <button onClick={onRetryHistory}>Retry history</button></div> : history.length === 0 ? <p>No history available.</p> : <div className="h-44 rounded-xl bg-white/[0.02] p-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={historyWithTime}>
            <defs>
              <linearGradient id="instVal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
            <XAxis
              dataKey="chartTime"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              stroke="#64748b"
              tick={{ fontSize: 12, fill: chartTheme.axis }}
              tickFormatter={formatChartDayTick}
              minTickGap={24}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 12, fill: chartTheme.axis }}
              tickFormatter={compactGbp}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={<ChartTooltip formatLabel={(label) => typeof label === "number" ? formatChartTooltipDay(label) : String(label ?? "")} />}
              cursor={{ stroke: "rgba(255,255,255,0.18)", strokeDasharray: 3 }}
            />
            <Area
              type="monotone"
              dataKey="value_gbp"
              stroke="#22d3ee"
              strokeWidth={2}
              fill="url(#instVal)"
              name="Value"
            />
            <Area
              type="monotone"
              dataKey="book_cost_gbp"
              stroke="#a78bfa"
              strokeWidth={1.25}
              fill="transparent"
              strokeDasharray="3 3"
              name="Book cost"
            />
            <Line
              type="monotone"
              dataKey="discretionary_cost_basis_gbp"
              stroke="#fbbf24"
              strokeWidth={1.25}
              strokeDasharray="4 3"
              dot={false}
              name="Discretionary basis"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>}

      {hasOrders && (
        <div className="min-h-0 flex-1">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            Orders
          </h3>
          {ordersLoading ? (
            <p className="text-xs text-slate-500">Loading…</p>
          ) : ordersError ? (
            <div role="alert">Orders unavailable. <button onClick={onRetryOrders}>Retry orders</button></div>
          ) : orders.length === 0 ? (
            <p className="text-xs text-slate-500">No matched orders.</p>
          ) : (
            <div className="max-h-44 space-y-1 overflow-auto pr-1">
              {orders.map((o) => (
                <OrderRow key={o.id} order={o} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function InstrumentDetailEmpty() {
  return (
    <div className="glass flex h-full min-h-[300px] flex-col items-center justify-center gap-2 rounded-2xl p-8 text-center">
      <Info size={22} className="text-slate-600" />
      <p className="text-sm text-slate-400">Select a holding</p>
      <p className="text-xs text-slate-600">
        Click any row to see its history and orders.
      </p>
    </div>
  );
}
