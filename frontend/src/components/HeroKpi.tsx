import { useEffect, useState } from "react";
import { animate, motion, useMotionValue } from "framer-motion";
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
  const mv = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const controls = animate(mv, value, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setDisplay(latest),
    });
    return () => controls.stop();
  }, [mv, value]);

  const sparkTone =
    trendPct != null ? (trendPct >= 0 ? "pos" : "neg") : "accent";

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="surface-card relative min-w-0 p-4 sm:p-5"
    >
      <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center">
        <div>
          <p className="text-sm font-medium text-slate-300">
            {label}
          </p>
          <div className="mt-3 flex items-end gap-3">
            <p
              className="tabular text-4xl font-semibold leading-none text-white sm:text-[44px]"
              style={{ letterSpacing: "-0.03em" }}
            >
              {toGbp(display)}
            </p>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <TrendChip value={trendPct ?? null} />
            {deltaAbs != null && (
              <span
                className={`tabular text-sm ${
                  deltaAbs >= 0 ? "text-pos" : "text-neg"
                }`}
              >
                {deltaAbs >= 0 ? "+" : ""}
                {toGbp(deltaAbs)}
              </span>
            )}
            {caption && (
              <span className="text-xs text-slate-500">{caption}</span>
            )}
          </div>
        </div>

        {sparkline && sparkline.length > 0 && (
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
    </motion.section>
  );
}
