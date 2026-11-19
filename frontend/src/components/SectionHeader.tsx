import type { ReactNode } from "react";

export function SectionHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <div className="min-w-0">
        <h2 className="tufte-label text-slate-200">{title}</h2>
        {description && (
          <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-slate-400">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="max-w-full">{actions}</div>}
    </div>
  );
}
