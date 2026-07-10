import { Percent } from "lucide-react";
import type { PortfolioReturnSummary } from "../lib/api";
import { StatCard } from "./StatCard";

const formatDate = (value: string): string => {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(year, month - 1, day));
};

export function PortfolioReturnCard({ summary }: { summary: PortfolioReturnSummary | undefined }) {
  const returnPct = summary?.modified_dietz_return_pct;
  if (summary == null || returnPct == null) {
    const notes = summary?.notes ?? [];
    const explanation = notes[notes.length - 1] ?? "Return data is not available for this selection.";
    return (
      <StatCard
        label="Estimated money-weighted return"
        value="Unavailable"
        tone="muted"
        sub={explanation}
        icon={<Percent size={14} />}
      />
    );
  }

  const period =
    summary.period_start && summary.period_end
      ? `${formatDate(summary.period_start)} – ${formatDate(summary.period_end)}`
      : "Available snapshot period";
  const formatted = `${returnPct > 0 ? "+" : ""}${returnPct.toFixed(2)}%`;

  return (
    <StatCard
      label="Estimated money-weighted return"
      value={formatted}
      tone={returnPct >= 0 ? "pos" : "neg"}
      sub={`Cumulative, not annualised · ${period} · ${summary.method}`}
      icon={<Percent size={14} />}
    />
  );
}
