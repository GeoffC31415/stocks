import type { ReactNode } from "react";
import { Sparkline } from "./Sparkline";
import { TrendChip } from "./TrendChip";
import { MetricCard, type MetricTone } from "./MetricCard";

type Tone = "accent" | "pos" | "neg" | "amber" | "muted";
const metricTone: Record<Tone, MetricTone> = {
  accent: "neutral", pos: "positive", neg: "negative", amber: "warning", muted: "neutral",
};

/** Compatibility adapter: existing panels share one semantic metric layout. */
export function StatCard({ label, value, sub, tone = "muted", trend, trendFormat,
  sparkline, sparklineKey, icon, emphasis = false }: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  trend?: number | null;
  trendFormat?: (v: number) => string;
  sparkline?: Array<Record<string, number | string | null>>;
  sparklineKey?: string;
  icon?: ReactNode;
  emphasis?: boolean;
}) {
  const sparkTone = tone === "pos" || tone === "neg" || tone === "amber" ? tone : "accent";
  return <MetricCard label={label} value={value} description={sub} tone={metricTone[tone]}
    icon={icon} emphasis={emphasis}
    action={trend != null ? <TrendChip value={trend} format={trendFormat} /> : undefined}>
    {sparkline && sparkline.length > 0 && <div className="mt-3">
      <Sparkline data={sparkline} dataKey={sparklineKey ?? "value"} tone={sparkTone} height={36} />
    </div>}
  </MetricCard>;
}
