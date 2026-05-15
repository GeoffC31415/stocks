import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  TrendingUp,
  TrendingDown,
  Calendar,
  Scale,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { api } from "../lib/api";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { MatchingWarningBanner } from "../components/MatchingWarningBanner";

function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  tone?: "neutral" | "gain" | "loss" | "accent";
}) {
  const toneClass =
    tone === "gain"
      ? "text-pos"
      : tone === "loss"
        ? "text-neg"
        : tone === "accent"
          ? "text-aurora-cyan"
          : "text-slate-300";

  return (
    <div className="rounded-xl bg-white/[0.02] border border-white/[0.05] p-4">
      <div className="flex items-center gap-2">
        {icon && <span className="text-slate-500">{icon}</span>}
        <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</p>
      </div>
      <p className={`mt-1 text-2xl font-semibold tabular ${toneClass}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function TaxYearSummary({ ty }: { ty: {
  tax_year: string;
  taxable_proceeds: number;
  taxable_cost: number;
  taxable_gain: number;
  taxable_loss: number;
  exempt_proceeds: number;
  exempt_cost: number;
  exempt_gain: number;
  exempt_loss: number;
  gain_count: number;
  loss_count: number;
  instrument_count: number;
  exempt_count: number;
} }) {
  const taxableNet = ty.taxable_gain - ty.taxable_loss;
  const exemptNet = ty.exempt_gain - ty.exempt_loss;

  return (
    <div className="rounded-xl bg-white/[0.02] border border-white/[0.05] p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-slate-500" />
          <span className="text-sm font-semibold text-white">{ty.tax_year}</span>
        </div>
        <span className={`text-sm font-semibold tabular ${taxableNet >= 0 ? "text-pos" : "text-neg"}`}>
          {taxableNet >= 0 ? "+" : ""}{toGbp(taxableNet)}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] text-slate-500">Proceeds</p>
          <p className="tabular text-sm text-slate-300">{toGbp(ty.taxable_proceeds)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Cost</p>
          <p className="tabular text-sm text-slate-300">{toGbp(ty.taxable_cost)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Gains</p>
          <p className="tabular text-sm text-pos">{toGbp(ty.taxable_gain)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500">Losses</p>
          <p className="tabular text-sm text-neg">{toGbp(ty.taxable_loss)}</p>
        </div>
      </div>

      {/* Exempt amounts */}
      {ty.exempt_count > 0 ? (
        <div className="mt-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 px-3 py-2">
          <div className="flex items-center gap-2">
            <ShieldCheck size={12} className="text-emerald-400" />
            <span className="text-[10px] font-medium text-emerald-300">Exempt (ISA)</span>
            <span className="text-[10px] text-slate-500">·</span>
            <span className="text-[10px] text-slate-400">{toGbp(ty.exempt_gain)} gains · {toGbp(ty.exempt_loss)} losses</span>
          </div>
        </div>
      ) : null}

      <p className="mt-2 text-[11px] text-slate-500">
        {ty.gain_count} gain{ty.gain_count !== 1 ? "s" : ""} · {ty.loss_count} loss{ty.loss_count !== 1 ? "es" : ""} · {ty.instrument_count - ty.exempt_count}/{ty.instrument_count} taxable instrument{ty.instrument_count !== 1 ? "s" : ""}
      </p>
    </div>
  );
}

function InstrumentDetail({ instrument }: { instrument: {
  instrument_id: number;
  security_name: string;
  identifier: string;
  account_name: string;
  is_exempt: boolean;
  total_proceeds_gbp: number;
  total_cost_gbp: number;
  total_gain_gbp: number;
  total_loss_gbp: number;
  net_gain_gbp: number;
  sales: Array<{
    order_id: number;
    order_date: string;
    quantity: number;
    proceeds_gbp: number;
    total_cost: number;
    realised_gain: number;
    matches: Array<{ source: string; order_id?: number | null; order_date?: string | null; security_name?: string | null; quantity: number; cost: number; proceeds: number }>;
  }>;
  tax_year_summaries: Array<{ tax_year: string; total_gain: number; total_loss: number }>;
} }) {
  const [expanded, setExpanded] = useState(false);
  const hasSales = instrument.sales.length > 0;
  const netGain = instrument.net_gain_gbp;

  return (
    <div className={`rounded-xl border overflow-hidden ${
      instrument.is_exempt
        ? "bg-emerald-500/[0.03] border-emerald-500/20"
        : "bg-white/[0.02] border-white/[0.05]"
    }`}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <FileText size={16} className={instrument.is_exempt ? "text-emerald-400" : "text-slate-500"} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-white truncate">{instrument.security_name}</p>
              {instrument.is_exempt && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-medium text-emerald-300 shrink-0">
                  <ShieldCheck size={10} />
                  ISA
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 truncate">{instrument.account_name} · {instrument.identifier}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          {hasSales && (
            <span className="text-sm tabular text-slate-400">{instrument.sales.length} sale{instrument.sales.length !== 1 ? "s" : ""}</span>
          )}
          <span className={`text-sm font-semibold tabular ${netGain >= 0 ? "text-pos" : "text-neg"}`}>
            {netGain >= 0 ? "+" : ""}{toGbp(netGain)}
          </span>
        </div>
      </button>

      {expanded && hasSales && (
        <div className="border-t border-white/[0.05]">
          {instrument.sales.map((sale) => (
            <div key={sale.order_id} className="px-4 py-3 border-b border-white/[0.03]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-slate-300">
                  {new Date(sale.order_date).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </span>
                <span className={`text-xs font-semibold tabular ${sale.realised_gain >= 0 ? "text-pos" : "text-neg"}`}>
                  {sale.realised_gain >= 0 ? "+" : ""}{toGbp(sale.realised_gain)}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <span className="text-slate-500">Qty: </span>
                  <span className="text-slate-300 tabular">{sale.quantity}</span>
                </div>
                <div>
                  <span className="text-slate-500">Proceeds: </span>
                  <span className="text-slate-300 tabular">{toGbp(sale.proceeds_gbp)}</span>
                </div>
                <div>
                  <span className="text-slate-500">Cost: </span>
                  <span className="text-slate-300 tabular">{toGbp(sale.total_cost)}</span>
                </div>
              </div>
              {sale.matches.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {sale.matches.map((m, i) => (
                    <span
                      key={i}
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        m.source === "same_day"
                          ? "bg-aurora-cyan/10 text-aurora-cyan"
                          : m.source === "b&f"
                            ? "bg-amber-400/10 text-amber-300"
                            : "bg-slate-500/10 text-slate-400"
                      }`}
                    >
                      {m.source === "same_day" ? "Same-day" : m.source === "b&f" ? "B&F" : "Pool"} · {m.quantity} · {toGbp(m.cost)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {instrument.tax_year_summaries.map((ty) => (
            <div key={ty.tax_year} className="px-4 py-2 bg-white/[0.01]">
              <span className="text-[10px] text-slate-500">Tax year {ty.tax_year}: </span>
              <span className={`text-[10px] font-medium ${ty.total_gain > ty.total_loss ? "text-pos" : ty.total_loss > ty.total_gain ? "text-neg" : "text-slate-400"}`}>
                {ty.total_gain > ty.total_loss ? "+" : ""}{toGbp(ty.total_gain - ty.total_loss)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CGT() {
  const { accountFilter } = usePreferences();

  const cgtQ = useQuery({
    queryKey: ["cgt", accountFilter],
    queryFn: () => api.getCgtSummary(accountFilter === "all" ? undefined : accountFilter),
  });

  const hasSales = cgtQ.data?.instruments.some((i) => i.sales.length > 0) ?? false;

  // Use taxable (non-ISA) totals for summary cards
  const taxableGain = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.taxable_gain, 0) ?? 0),
    [cgtQ.data],
  );
  const taxableLoss = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.taxable_loss, 0) ?? 0),
    [cgtQ.data],
  );
  const exemptGain = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.exempt_gain, 0) ?? 0),
    [cgtQ.data],
  );
  const exemptLoss = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.exempt_loss, 0) ?? 0),
    [cgtQ.data],
  );

  const exemptGainAmount = 3000; // 2025-26 CGT annual exempt amount
  const taxableNetGain = taxableGain - taxableLoss;
  const taxableGainAfterExempt = Math.max(0, taxableNetGain - exemptGainAmount);
  const totalProceeds = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.taxable_proceeds, 0) ?? 0),
    [cgtQ.data],
  );
  const totalCost = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.taxable_cost, 0) ?? 0),
    [cgtQ.data],
  );

  const totalExemptCount = useMemo(
    () => (cgtQ.data?.tax_year_totals.reduce((s, t) => s + t.exempt_count, 0) ?? 0),
    [cgtQ.data],
  );

  if (!hasSales && cgtQ.isSuccess) {
    return (
      <div className="space-y-5">
        <MatchingWarningBanner />
        <div className="glass mx-auto max-w-xl rounded-2xl p-8 text-center">
          <Scale className="mx-auto text-slate-500" size={28} />
          <h2 className="mt-3 text-lg font-semibold text-white">No sales yet</h2>
          <p className="mt-2 text-sm text-slate-400">
            Import order history with sell orders to calculate CGT.
          </p>
        </div>
      </div>
    );
  }

  if (cgtQ.isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-400">
        <span className="text-sm">Loading CGT data…</span>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <MatchingWarningBanner />

      <div>
        <h1 className="text-2xl font-semibold text-white" style={{ letterSpacing: "-0.02em" }}>
          Capital Gains Tax
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          UK CGT matching: same-day rule, bed &amp; breakfasting (30-day), and Section&nbsp;104 pool.
          {totalExemptCount > 0 ? (
            <span className="inline-flex items-center gap-1 ml-1">
              <ShieldCheck size={14} className="text-emerald-400" />
              <span className="text-emerald-300">{totalExemptCount} instrument{totalExemptCount !== 1 ? "s" : ""} ISA-exempt</span>
            </span>
          ) : null}
        </p>
      </div>

      {/* Summary cards - taxable only */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Taxable gains"
          value={toGbp(taxableGain)}
          icon={<TrendingUp size={14} />}
          tone="gain"
        />
        <StatCard
          label="Taxable losses"
          value={toGbp(taxableLoss)}
          icon={<TrendingDown size={14} />}
          tone="loss"
        />
        <StatCard
          label="Net taxable"
          value={toGbp(taxableNetGain)}
          sub={`${toGbp(exemptGainAmount)} annual exemption`}
          tone={taxableNetGain >= 0 ? "gain" : "neutral"}
        />
        <StatCard
          label="Taxable after exemption"
          value={toGbp(taxableGainAfterExempt)}
          sub={taxableGainAfterExempt > 0 ? "Potential CGT liability" : "Within exemption"}
          tone="accent"
        />
      </div>

      {/* Exempt summary */}
      {exemptGain > 0 || exemptLoss > 0 ? (
        <div className="rounded-xl bg-emerald-500/5 border border-emerald-500/20 p-4">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-emerald-400" />
            <span className="text-sm font-medium text-emerald-200">ISA-exempt gains &amp; losses</span>
          </div>
          <p className="mt-2 text-sm text-slate-400">
            {toGbp(exemptGain)} gains · {toGbp(exemptLoss)} losses — not subject to CGT
          </p>
        </div>
      ) : null}

      {/* Tax year summaries */}
      {cgtQ.data?.tax_year_totals.length ? (
        <>
          <div>
            <h2 className="text-base font-semibold text-white">Tax year summary</h2>
            <p className="text-xs text-slate-500">Taxable gains/losses by tax year. ISA gains shown separately.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cgtQ.data.tax_year_totals.map((ty) => (
              <TaxYearSummary key={ty.tax_year} ty={ty} />
            ))}
          </div>
        </>
      ) : null}

      {/* Per-instrument detail */}
      {cgtQ.data?.instruments.length ? (
        <>
          <div>
            <h2 className="text-base font-semibold text-white">Instruments</h2>
            <p className="text-xs text-slate-500">Click to expand sale details.</p>
          </div>
          <div className="space-y-2">
            {cgtQ.data.instruments.map((inst) => (
              <InstrumentDetail key={inst.instrument_id} instrument={inst} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
