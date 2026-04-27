import { motion } from "framer-motion";
import type { ReactNode } from "react";

export type Segment<K extends string> = {
  key: K;
  label: ReactNode;
  count?: number;
};

type Tone = "accent" | "amber" | "violet" | "neg";

const TONE_BG: Record<Tone, string> = {
  accent: "bg-aurora-accent shadow-glow-accent",
  amber: "bg-gradient-to-r from-amber-500 to-amber-400 shadow-[0_0_24px_rgba(251,191,36,0.35)]",
  violet: "bg-gradient-to-r from-violet-500 to-violet-400 shadow-[0_0_24px_rgba(167,139,250,0.35)]",
  neg: "bg-gradient-to-r from-rose-500 to-rose-400 shadow-[0_0_24px_rgba(248,113,113,0.35)]",
};

export function SegmentedControl<K extends string>({
  value,
  segments,
  onChange,
  tone = "accent",
  layoutId,
  size = "md",
}: {
  value: K;
  segments: Segment<K>[];
  onChange: (key: K) => void;
  tone?: Tone;
  layoutId: string;
  size?: "sm" | "md";
}) {
  const padding = size === "sm" ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-xs";
  const radius = size === "sm" ? "rounded-md" : "rounded-full";
  const containerRadius = size === "sm" ? "rounded-lg" : "rounded-full";

  return (
    <div
      className={`relative inline-flex gap-1 border border-white/[0.06] bg-aurora-base/60 p-1 ${containerRadius}`}
    >
      {segments.map((s) => {
        const isActive = s.key === value;
        return (
          <button
            key={s.key}
            type="button"
            onClick={() => onChange(s.key)}
            className={`relative ${radius} ${padding} font-medium transition-colors ${
              isActive
                ? "text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId={layoutId}
                className={`absolute inset-0 -z-10 ${radius} ${TONE_BG[tone]}`}
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
              />
            )}
            <span className="relative flex items-center gap-1.5">
              {s.label}
              {s.count != null && (
                <span
                  className={`tabular text-[10px] ${
                    isActive ? "text-white/80" : "text-slate-500"
                  }`}
                >
                  {s.count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
