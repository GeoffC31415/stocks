type NullableNumber = number | null | undefined;
const finite = (value: NullableNumber): value is number => value != null && Number.isFinite(value);
const roundedZero = (value: number, digits: number) => Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value;
const currency = (digits: number) => new Intl.NumberFormat("en-GB", {
  style: "currency", currency: "GBP", minimumFractionDigits: digits, maximumFractionDigits: digits,
});
const wholeGbp = currency(0), exactGbp = currency(2);
const axisGbp = new Intl.NumberFormat("en-GB", {
  style: "currency", currency: "GBP", notation: "compact", maximumFractionDigits: 1,
});

/** Retains existing whole-pound display rounding; null is never zero. */
export const toGbp = (value: NullableNumber): string => finite(value) ? wholeGbp.format(roundedZero(value, 0)) : "—";
export const toGbpExact = (value: NullableNumber): string => finite(value) ? exactGbp.format(roundedZero(value, 2)) : "—";
export const compactGbp = (value: NullableNumber): string => finite(value)
  ? axisGbp.format(roundedZero(value, 0)).replace(/K$/, "k").replace(/M$/, "m").replace(/B$/, "bn") : "—";
export const signedGbp = (value: NullableNumber): string => {
  if (!finite(value)) return "—";
  const rounded = roundedZero(value, 0);
  return `${rounded > 0 ? "+" : rounded < 0 ? "−" : ""}${toGbp(Math.abs(rounded))}`;
};
export const pct = (value: NullableNumber): string => finite(value) ? `${roundedZero(value, 2).toFixed(2)}%` : "—";

export const formatOrderDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isFinite(date.getTime()) ? date.toLocaleDateString("en-GB", {
    timeZone: "UTC", day: "numeric", month: "short", year: "numeric",
  }) : "—";
};

export const DRIP_DEFAULT = 1000;
