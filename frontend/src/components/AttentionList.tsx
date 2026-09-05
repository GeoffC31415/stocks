import { useState } from "react";
import type { AttentionItem } from "../lib/dataQualityApi";

const STORAGE = "portfolio.attentionDismissals.v1";
function readDismissals(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE) ?? "[]");
    return Array.isArray(value) ? value.filter((key): key is string => typeof key === "string").slice(-200) : [];
  } catch { return []; }
}
export function AttentionList({ items }: { items: AttentionItem[] }) {
  const [dismissed, setDismissed] = useState(readDismissals);
  const save = (keys: string[]) => {
    setDismissed(keys);
    try { localStorage.setItem(STORAGE, JSON.stringify(keys)); } catch { /* Optional local preference. */ }
  };
  const visible = items.filter((item) => item.severity === "critical" || !item.dismissible || !dismissed.includes(item.evidence_key));
  const hidden = items.length - visible.length;
  return <div className="space-y-3">
    {visible.map((item) => <article key={item.id} role={item.severity === "critical" ? "alert" : undefined} className="border-l-2 border-amber-300/40 pl-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-200">{item.title}</h3>
        <span className="text-xs text-slate-400">{item.category === "rule" ? "Personal rule" : "Data fact"}</span>
      </div>
      <ul className="mt-1 space-y-1 text-xs text-slate-400">{item.evidence.map((fact) => <li key={fact}>{fact}</li>)}</ul>
      <div className="mt-1 flex flex-wrap items-center gap-4 text-xs">
        <a className="inline-flex min-h-9 items-center text-cyan-200 underline" href={item.action_href}>Investigate: {item.title}</a>
        {item.dismissible && item.severity !== "critical" && <button type="button" className="min-h-9 text-slate-400 underline"
          onClick={() => save([...dismissed, item.evidence_key].slice(-200))}>Dismiss unchanged reminder</button>}
      </div>
    </article>)}
    {hidden > 0 && <p className="text-xs text-slate-400">{hidden} unchanged reminder{hidden === 1 ? "" : "s"} dismissed.
      <button type="button" className="ml-2 min-h-9 underline" onClick={() => save([])}>Restore reminders</button></p>}
    {items.length === 0 && <p className="text-sm text-slate-300">No reminders in this list.</p>}
  </div>;
}
