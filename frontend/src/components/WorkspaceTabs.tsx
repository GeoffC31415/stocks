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
}: {
  tabs: WorkspaceTab[];
  label: string;
  param?: string;
}) {
  const [params, setParams] = useSearchParams();
  const selected = params.get(param) ?? tabs[0]?.key;

  const select = (key: string) => {
    const next = new URLSearchParams(params);
    next.set(param, key);
    setParams(next, { replace: true });
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex max-w-full flex-wrap gap-1 rounded-xl border border-white/[0.06] bg-white/[0.025] p-1"
    >
      {tabs.map((tab) => {
        const active = tab.key === selected;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
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
            className={`min-h-9 min-w-0 max-w-full rounded-lg [overflow-wrap:anywhere] px-3 text-xs font-medium transition-colors ${
              active
                ? "bg-white/[0.09] text-white shadow-sm"
                : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200"
            }`}
          >
            {tab.label}
            {tab.count != null ? (
              <span className="ml-1.5 tabular text-[10px] text-slate-500">{tab.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
