export const toGbp = (value: number | null | undefined): string =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  }).format(value ?? 0);

export const pct = (value: number | null | undefined): string =>
  `${(value ?? 0).toFixed(2)}%`;

export const formatOrderDate = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export const DRIP_DEFAULT = 1000;
