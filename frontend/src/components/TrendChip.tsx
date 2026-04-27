import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export function TrendChip({
  value,
  suffix = "%",
  format,
  neutralBelow = 0.001,
}: {
  value: number | null | undefined;
  suffix?: string;
  format?: (v: number) => string;
  neutralBelow?: number;
}) {
  if (value == null || isNaN(value)) {
    return (
      <span className="chip chip-muted">
        <Minus size={12} />
        <span>—</span>
      </span>
    );
  }

  const isPos = value > neutralBelow;
  const isNeg = value < -neutralBelow;
  const display = format
    ? format(value)
    : `${value >= 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;

  if (!isPos && !isNeg) {
    return (
      <span className="chip chip-muted tabular">
        <Minus size={12} />
        {display}
      </span>
    );
  }

  return (
    <span className={`chip tabular ${isPos ? "chip-pos" : "chip-neg"}`}>
      {isPos ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
      {display}
    </span>
  );
}
