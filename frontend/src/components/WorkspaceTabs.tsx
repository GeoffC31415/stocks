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
      className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.025] p-1"
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
            className={`min-h-9 whitespace-nowrap rounded-lg px-3 text-xs font-medium transition-colors ${
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
