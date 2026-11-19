import { useId, type ReactNode } from "react";

export type MetricTone = "neutral" | "positive" | "negative" | "warning";
const toneClass: Record<MetricTone, string> = {
  neutral: "text-slate-100",
  positive: "text-pos",
  negative: "text-neg",
  warning: "text-amber-300",
};

export function MetricCard({
  label,
  value,
  description,
  tone = "neutral",
  icon,
  action,
  children,
  emphasis = false,
}: {
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
  return (
    <article
      aria-labelledby={id}
      className="surface-card flex min-w-0 flex-col justify-between px-3.5 py-3"
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          id={id}
          className="tufte-label flex min-w-0 items-center gap-1.5"
        >
          {icon && <span aria-hidden="true" className="text-slate-500">{icon}</span>}
          {label}
        </h3>
        {action}
      </div>
      <p
        className={`num mt-1.5 font-semibold tracking-tight ${
          emphasis ? "text-2xl sm:text-3xl" : "text-xl leading-tight"
        } ${toneClass[tone]}`}
      >
        {value}
      </p>
      {description && (
        <p className="num mt-1 text-[11px] leading-snug text-slate-400">{description}</p>
      )}
      {children}
    </article>
  );
}
