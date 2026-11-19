import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

export type WorkspaceTab = {
  key: string;
  label: string;
  count?: number;
};

export function WorkspaceTabs({
  tabs,
  label,
  param = "tab",
  validHiddenTabs = [],
}: {
  tabs: WorkspaceTab[];
  label: string;
  param?: string;
  validHiddenTabs?: string[];
}) {
  const [params, setParams] = useSearchParams();
  const raw = params.get(param);
  const selected = raw != null && (tabs.some(tab => tab.key === raw) || validHiddenTabs.includes(raw)) ? raw : tabs[0]?.key;
  useEffect(() => {
    if (raw != null && (raw !== selected || params.getAll(param).length > 1) && selected) {
      const next = new URLSearchParams(params); next.set(param, selected); setParams(next, {replace: true});
    }
  }, [raw, selected, params, param, setParams]);

  const select = (key: string) => {
    const next = new URLSearchParams(params);
    next.set(param, key);
    setParams(next);
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex max-w-full flex-wrap gap-1 border-b border-white/[0.08]"
    >
      {tabs.map((tab) => {
        const active = tab.key === selected;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`workspace-tab-${tab.key}`}
            aria-controls="workspace-panel"
            tabIndex={active || (validHiddenTabs.includes(selected ?? "") && tab === tabs[0]) ? 0 : -1}
            aria-selected={active}
            onClick={() => select(tab.key)}
            onFocus={(event) => event.currentTarget.scrollIntoView?.({ block: "nearest", inline: "nearest" })}
            onKeyDown={(event) => {
              const index = tabs.indexOf(tab);
              const next = event.key === "ArrowRight" ? (index + 1) % tabs.length
                : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length
                : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
              if (next == null) return;
              event.preventDefault();
              select(tabs[next].key);
              event.currentTarget.parentElement?.querySelectorAll("button")[next]?.focus();
            }}
            className={`relative min-h-10 min-w-0 max-w-full [overflow-wrap:anywhere] px-3.5 text-xs font-medium transition-colors ${
              active
                ? "text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
            {tab.count != null ? (
              <span className="ml-1.5 rounded-full bg-white/[0.06] px-1.5 py-0.5 tabular text-[10px] text-slate-400">
                {tab.count}
              </span>
            ) : null}
            {active ? (
              <span
                aria-hidden="true"
                className="absolute inset-x-1 -bottom-px h-0.5 rounded-full bg-sky-400"
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
