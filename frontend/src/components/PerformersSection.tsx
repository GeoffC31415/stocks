import { TrendingDown, TrendingUp } from "lucide-react";
import { pct } from "../lib/formatters";
import type { Instrument } from "../lib/api";

function PerformerList({
  title,
  icon: Icon,
  items,
  colorClass,
  onSelect,
}: {
  title: string;
  icon: typeof TrendingUp;
  items: Instrument[];
  colorClass: string;
  onSelect: (id: number) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Icon size={16} className={colorClass} />
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      </div>
      <ul className="space-y-1.5">
        {items.map((row) => (
          <li
            key={row.id}
            className="flex cursor-pointer items-center justify-between rounded-lg bg-slate-900/40 px-3 py-2 transition-colors hover:bg-slate-800/50"
            onClick={() => onSelect(row.id)}
          >
            <span className="mr-3 min-w-0 truncate text-sm text-slate-300">
              {row.security_name}
            </span>
            <span className={`shrink-0 font-medium ${colorClass}`}>
              {pct(row.latest_pct_change)}
            </span>
          </li>
        ))}
      </ul>
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
    <div className="grid gap-6 lg:grid-cols-2">
      <PerformerList
        title="Poor performers"
        icon={TrendingDown}
        items={worst}
        colorClass="text-rose-400"
        onSelect={onSelect}
      />
      <PerformerList
        title="Strong performers"
        icon={TrendingUp}
        items={best}
        colorClass="text-emerald-400"
        onSelect={onSelect}
      />
    </div>
  );
}
