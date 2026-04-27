import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { Sparkline } from "./Sparkline";
import { TrendChip } from "./TrendChip";

type Tone = "accent" | "pos" | "neg" | "amber" | "muted";

type SparklineData = Array<Record<string, number | string | null>>;

export function StatCard({
  label,
  value,
  sub,
  tone = "muted",
  trend,
  trendFormat,
  sparkline,
  sparklineKey,
  icon,
  emphasis = false,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  trend?: number | null;
  trendFormat?: (v: number) => string;
  sparkline?: SparklineData;
  sparklineKey?: string;
  icon?: ReactNode;
  emphasis?: boolean;
}) {
  const valueClass =
    tone === "pos"
      ? "text-pos"
      : tone === "neg"
        ? "text-neg"
        : tone === "amber"
          ? "text-amber-300"
          : tone === "accent"
            ? "text-aurora-cyan"
            : "text-white";

  const sparkTone =
    tone === "pos" || tone === "neg" || tone === "amber" ? tone : "accent";

  return (
    <motion.article
      whileHover={{ y: -2 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className={`glass glass-hover gradient-border relative overflow-hidden rounded-2xl p-5 ${
        emphasis ? "ring-1 ring-white/[0.06]" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {icon && <span className="text-slate-500">{icon}</span>}
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            {label}
          </p>
        </div>
        {trend != null && <TrendChip value={trend} format={trendFormat} />}
      </div>

      <p
        className={`tabular mt-3 text-2xl font-semibold ${valueClass}`}
        style={{ letterSpacing: "-0.01em" }}
      >
        {value}
      </p>

      {sub && (
        <p className="tabular mt-1 text-xs text-slate-500">{sub}</p>
      )}

      {sparkline && sparkline.length > 0 && (
        <div className="mt-3 -mx-1">
          <Sparkline
            data={sparkline}
            dataKey={sparklineKey ?? "value"}
            tone={sparkTone}
            height={36}
          />
        </div>
      )}
    </motion.article>
  );
}
