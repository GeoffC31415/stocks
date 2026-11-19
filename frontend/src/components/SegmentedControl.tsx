import { motion } from "framer-motion";
import type { ReactNode } from "react";

export type Segment<K extends string> = {
  key: K;
  label: ReactNode;
  count?: number;
};

type Tone = "accent" | "amber" | "violet" | "neg";

const TONE_BG: Record<Tone, string> = {
  accent: "bg-white/[0.12]",
  amber: "bg-amber-500/20",
  violet: "bg-sky-500/20",
  neg: "bg-rose-500/20",
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
  const padding = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";
  const minH = size === "sm" ? "min-h-6" : "min-h-7";

  return (
    <div
      className="relative inline-flex max-w-full flex-wrap border border-white/[0.09] bg-white/[0.02] p-0.5"
    >
      {segments.map((s) => {
        const isActive = s.key === value;
        return (
          <button
            key={s.key}
            type="button"
            onClick={() => onChange(s.key)}
            aria-pressed={isActive}
            className={`num relative ${minH} min-w-0 max-w-full [overflow-wrap:anywhere] ${padding} font-medium transition-colors ${
              isActive
                ? "text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId={layoutId}
                className={`absolute inset-0 -z-10 ${TONE_BG[tone]}`}
                transition={{ type: "spring", stiffness: 460, damping: 36 }}
              />
            )}
            <span className="relative flex min-w-0 items-center gap-1.5">
              {s.label}
              {s.count != null && (
                <span
                  className={`num text-[10px] ${
                    isActive ? "text-slate-200" : "text-slate-500"
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
