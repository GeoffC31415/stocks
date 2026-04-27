import { TrendingDown, TrendingUp } from "lucide-react";
import { motion } from "framer-motion";
import { pct } from "../lib/formatters";
import type { Instrument } from "../lib/api";

function PerformerList({
  title,
  icon: Icon,
  items,
  variant,
  onSelect,
}: {
  title: string;
  icon: typeof TrendingUp;
  items: Instrument[];
  variant: "pos" | "neg";
  onSelect: (id: number) => void;
}) {
  const colorClass = variant === "pos" ? "text-pos" : "text-neg";
  const dotClass = variant === "pos" ? "bg-pos" : "bg-neg";
  const glowStyle =
    variant === "pos"
      ? {
          background:
            "radial-gradient(60% 80% at 0% 100%, rgba(52,211,153,0.18), transparent 70%)",
        }
      : {
          background:
            "radial-gradient(60% 80% at 100% 0%, rgba(248,113,113,0.18), transparent 70%)",
        };

  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={glowStyle}
      />
      <div className="relative">
        <div className="mb-4 flex items-center gap-2">
          <Icon size={16} className={colorClass} />
          <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
          <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-600">
            % change
          </span>
        </div>

        {items.length === 0 ? (
          <p className="py-6 text-center text-xs text-slate-500">
            No data yet.
          </p>
        ) : (
          <motion.ul
            className="space-y-1.5"
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.04 } },
            }}
          >
            {items.map((row) => (
              <motion.li
                key={row.id}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="group flex cursor-pointer items-center gap-3 rounded-xl bg-white/[0.02] px-3 py-2.5 transition-colors hover:bg-white/[0.05]"
                onClick={() => onSelect(row.id)}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
                <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                  {row.security_name}
                </span>
                <span className={`tabular shrink-0 text-sm font-semibold ${colorClass}`}>
                  {pct(row.latest_pct_change)}
                </span>
              </motion.li>
            ))}
          </motion.ul>
        )}
      </div>
    </div>
  );
}

export function PerformersSection({
  worst,
  best,
  onSelect,
}: {
  worst: Instrument[];
  best: Instrument[];
  onSelect: (id: number) => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <PerformerList
        title="Poor performers"
        icon={TrendingDown}
        items={worst}
        variant="neg"
        onSelect={onSelect}
      />
      <PerformerList
        title="Strong performers"
        icon={TrendingUp}
        items={best}
        variant="pos"
        onSelect={onSelect}
      />
    </div>
  );
}
