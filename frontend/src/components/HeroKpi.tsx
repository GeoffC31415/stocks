import { Sparkline } from "./Sparkline";
import { TrendChip } from "./TrendChip";
import { toGbp } from "../lib/formatters";

export function HeroKpi({
  label,
  value,
  trendPct,
  deltaAbs,
  sparkline,
  sparklineKey = "value",
  caption,
}: {
  label: string;
  value: number;
  trendPct?: number | null;
  deltaAbs?: number | null;
  sparkline?: Array<Record<string, number | string | null>>;
  sparklineKey?: string;
  caption?: string;
}) {
  const sparkTone =
    trendPct != null ? (trendPct >= 0 ? "pos" : "neg") : "accent";

  return (
    <section
      className="surface-card relative min-w-0 overflow-hidden p-5"
      style={{
        background:
          "linear-gradient(180deg, rgba(56, 189, 248, 0.065) 0%, rgba(16, 20, 29, 0.98) 65%)",
      }}
    >
      <div className="relative grid gap-3 lg:items-center">
        <div>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-slate-400">
              {label}
            </p>
            {caption && (
              <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[11px] text-slate-400">
                {caption}
              </span>
            )}
          </div>
          <div className="mt-2.5 flex items-baseline gap-3">
            <p
              className="tabular text-4xl font-semibold leading-none text-white sm:text-[42px]"
              style={{ letterSpacing: "-0.035em" }}
            >
              {toGbp(value)}
            </p>
          </div>
          {(trendPct != null || deltaAbs != null) && (
            <div className="mt-3 flex flex-wrap items-center gap-2.5">
              {trendPct != null && <TrendChip value={trendPct} />}
              {deltaAbs != null && (
                <span
                  className={`tabular text-sm font-medium ${
                    deltaAbs >= 0 ? "text-pos" : "text-neg"
                  }`}
                >
                  {deltaAbs >= 0 ? "+" : ""}
                  {toGbp(deltaAbs)}
                </span>
              )}
            </div>
          )}
        </div>

        {sparkline && sparkline.length > 1 && (
          <div className="relative h-24">
            <Sparkline
              data={sparkline}
              dataKey={sparklineKey}
              tone={sparkTone}
              height={96}
            />
          </div>
        )}
      </div>
    </section>
  );
}
