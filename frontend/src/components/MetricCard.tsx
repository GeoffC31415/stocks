import { useId, type ReactNode } from "react";

export type MetricTone = "neutral" | "positive" | "negative" | "warning";
const toneClass: Record<MetricTone, string> = {
  neutral: "text-slate-100", positive: "text-pos", negative: "text-neg", warning: "text-amber-200",
};

export function MetricCard({ label, value, description, tone = "neutral", icon, action, children, emphasis = false }: {
  label: string;
  value: ReactNode;
  description?: ReactNode;
  tone?: MetricTone;
  icon?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  emphasis?: boolean;
}) {
  const id = useId();
  return <article aria-labelledby={id} className="surface-card min-w-0 p-4 sm:p-5">
    <div className="flex items-start justify-between gap-3">
      <h3 id={id} className="flex min-w-0 items-center gap-2 text-sm font-medium text-slate-300">
        {icon && <span aria-hidden="true">{icon}</span>}{label}
      </h3>
      {action}
    </div>
    <p className={`tabular mt-2 font-semibold ${emphasis ? "text-4xl" : "text-2xl"} ${toneClass[tone]}`}>{value}</p>
    {description && <p className="mt-1 text-xs leading-relaxed text-slate-400">{description}</p>}
    {children}
  </article>;
}
