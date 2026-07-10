import type { Instrument } from "./api";

export type AllocationDimension = "asset_class" | "sector" | "region";

export type AllocationCategory = {
  label: string;
  value: number;
  weightPct: number;
  count: number;
};

export type AllocationAnalysis = {
  totalValue: number;
  top1Pct: number;
  top5Pct: number;
  hhi: number;
  categories: AllocationCategory[];
  holdings: Array<{
    id: number;
    label: string;
    identifier: string;
    value: number;
    weightPct: number;
  }>;
};

const round = (value: number, places = 2) => {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
};

export function calculateAllocation(
  instruments: Instrument[],
  dimension: AllocationDimension,
): AllocationAnalysis {
  const investable = instruments
    .filter(
      (instrument) =>
        !instrument.is_cash &&
        !instrument.closed_at &&
        (instrument.latest_value_gbp ?? 0) > 0,
    )
    .map((instrument) => ({
      instrument,
      value: instrument.latest_value_gbp ?? 0,
    }))
    .sort((a, b) => b.value - a.value);

  const totalValue = investable.reduce((sum, row) => sum + row.value, 0);
  const holdings = investable.map(({ instrument, value }) => ({
    id: instrument.id,
    label: instrument.security_name,
    identifier: instrument.identifier,
    value: round(value),
    weightPct: totalValue > 0 ? round((value / totalValue) * 100) : 0,
  }));
  const top1Pct = holdings[0]?.weightPct ?? 0;
  const top5Pct = round(holdings.slice(0, 5).reduce((sum, row) => sum + row.weightPct, 0));
  const hhi = round(holdings.reduce((sum, row) => sum + row.weightPct ** 2, 0));

  const grouped = new Map<string, { value: number; count: number }>();
  for (const { instrument, value } of investable) {
    const label = instrument[dimension]?.trim() || "Unclassified";
    const current = grouped.get(label) ?? { value: 0, count: 0 };
    current.value += value;
    current.count += 1;
    grouped.set(label, current);
  }
  const categories = [...grouped.entries()]
    .map(([label, row]) => ({
      label,
      value: round(row.value),
      weightPct: totalValue > 0 ? round((row.value / totalValue) * 100) : 0,
      count: row.count,
    }))
    .sort((a, b) => b.value - a.value);

  return {
    totalValue: round(totalValue),
    top1Pct,
    top5Pct,
    hhi,
    categories,
    holdings,
  };
}
