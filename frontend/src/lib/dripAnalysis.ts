import type { Order } from "./api";

export type DripAnalysis = {
  total: number;
  trailing12m: number;
  prior12m: number;
  growthPct: number | null;
  count: number;
  byYear: Array<{ year: number; total: number; count: number }>;
  byInstrument: Array<{ name: string; total: number; count: number }>;
};

const startOfUtcDay = (date: Date) =>
  new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));

const yearsBefore = (date: Date, years: number) =>
  new Date(Date.UTC(date.getUTCFullYear() - years, date.getUTCMonth(), date.getUTCDate()));

const round = (value: number) => Math.round(value * 100) / 100;

export function calculateDripAnalysis(orders: Order[], asOf = new Date()): DripAnalysis {
  const end = startOfUtcDay(asOf);
  const trailingStart = yearsBefore(end, 1);
  const priorStart = yearsBefore(end, 2);
  const dripOrders = orders.filter(
    (order) => order.is_drip && order.side.toLowerCase() === "buy",
  );

  let total = 0;
  let trailing12m = 0;
  let prior12m = 0;
  const years = new Map<number, { total: number; count: number }>();
  const instruments = new Map<string, { total: number; count: number }>();

  for (const order of dripOrders) {
    const amount = order.cost_proceeds_gbp ?? 0;
    const date = new Date(order.order_date);
    total += amount;
    if (date >= trailingStart && date <= end) trailing12m += amount;
    else if (date >= priorStart && date < trailingStart) prior12m += amount;

    const year = date.getUTCFullYear();
    const yearRow = years.get(year) ?? { total: 0, count: 0 };
    yearRow.total += amount;
    yearRow.count += 1;
    years.set(year, yearRow);

    const instrumentRow = instruments.get(order.security_name) ?? { total: 0, count: 0 };
    instrumentRow.total += amount;
    instrumentRow.count += 1;
    instruments.set(order.security_name, instrumentRow);
  }

  return {
    total: round(total),
    trailing12m: round(trailing12m),
    prior12m: round(prior12m),
    growthPct: prior12m > 0 ? round(((trailing12m - prior12m) / prior12m) * 100) : null,
    count: dripOrders.length,
    byYear: [...years.entries()]
      .map(([year, row]) => ({ year, total: round(row.total), count: row.count }))
      .sort((a, b) => a.year - b.year),
    byInstrument: [...instruments.entries()]
      .map(([name, row]) => ({ name, total: round(row.total), count: row.count }))
      .sort((a, b) => b.total - a.total),
  };
}
