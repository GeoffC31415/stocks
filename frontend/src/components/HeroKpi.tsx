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
      className="glass relative overflow-hidden rounded-3xl p-6 sm:p-8"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full blur-3xl opacity-60"
        style={{
          background:
            "radial-gradient(circle, rgba(167, 139, 250, 0.35) 0%, rgba(34, 211, 238, 0.18) 50%, transparent 75%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)",
        }}
      />

      <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
            {label}
          </p>
          <div className="mt-3 flex items-end gap-3">
            <p
              className="tabular text-5xl font-semibold leading-none text-white sm:text-6xl"
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
          <div className="relative h-32 sm:h-40">
            <Sparkline
              data={sparkline}
              dataKey={sparklineKey}
              tone={sparkTone}
              height={160}
            />
          </div>
        )}
      </div>
    </motion.section>
  );
}
