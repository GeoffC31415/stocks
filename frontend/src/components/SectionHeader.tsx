import type { ReactNode } from "react";

export function SectionHeader({ title, description, actions }: {
  title: string; description?: ReactNode; actions?: ReactNode;
}) {
  return <div className="flex flex-wrap items-start justify-between gap-3">
    <div className="min-w-0">
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {description && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-400">{description}</p>}
    </div>
    {actions && <div className="max-w-full">{actions}</div>}
  </div>;
}
