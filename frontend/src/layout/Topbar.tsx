import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Calendar, Settings2, Upload } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { toGbp, formatOrderDate } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { SegmentedControl, type Segment } from "../components/SegmentedControl";

export function Topbar() {
  const navigate = useNavigate();
  const { dripThreshold, setDripThreshold, accountFilter, setAccountFilter } = usePreferences();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(String(dripThreshold));
  const popoverRef = useRef<HTMLDivElement>(null);

  const summaryQ = useQuery({
    queryKey: ["summary"],
    queryFn: api.getSummary,
  });

  useEffect(() => {
    setDraft(String(dripThreshold));
  }, [dripThreshold, open]);

  const accountNames = useMemo(
    () => Object.keys(summaryQ.data?.by_account ?? {}).sort(),
    [summaryQ.data?.by_account],
  );
  const accountSegments: Segment<string>[] = useMemo(
    () => [
      { key: "all", label: "All" },
      ...accountNames.map((name) => ({ key: name, label: name })),
    ],
    [accountNames],
  );

  useEffect(() => {
    if (accountFilter === "all" || accountNames.length === 0) return;
    if (!accountNames.includes(accountFilter)) setAccountFilter("all");
  }, [accountFilter, accountNames, setAccountFilter]);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const apply = () => {
    const parsed = parseFloat(draft);
    if (!isNaN(parsed) && parsed >= 0) setDripThreshold(parsed);
    setOpen(false);
  };

  const asOf = summaryQ.data?.as_of_date;

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-white/[0.05] bg-aurora-base/60 px-6 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <Calendar size={14} className="text-slate-500" />
        <span className="text-xs text-slate-500">Last snapshot</span>
        <span className="chip chip-accent tabular">
          {asOf ? formatOrderDate(asOf) : "—"}
        </span>
      </div>

      <div className="flex items-center gap-3">
        {accountSegments.length > 1 ? (
          <SegmentedControl
            layoutId="account-filter"
            value={accountFilter}
            onChange={setAccountFilter}
            tone="violet"
            size="sm"
            segments={accountSegments}
          />
        ) : null}

        <div className="relative" ref={popoverRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
          >
            <Settings2 size={14} className="text-slate-400" />
            <span className="text-slate-400">DRIP threshold</span>
            <span className="tabular text-amber-300">
              {toGbp(dripThreshold)}
            </span>
          </button>

          {open && (
            <div className="absolute right-0 top-full mt-2 w-72 rounded-xl border border-white/[0.08] bg-aurora-surface/95 p-4 shadow-glass backdrop-blur-xl">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                DRIP threshold (£)
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                Buys below this amount are classified as DRIP.
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && apply()}
                  className="tabular flex-1 rounded-lg border border-white/[0.08] bg-aurora-base/70 px-3 py-2 text-sm text-white focus:border-aurora-cyan/60 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={apply}
                  className="rounded-lg bg-aurora-accent px-3 py-2 text-xs font-semibold text-white shadow-glow-accent"
                >
                  Apply
                </button>
              </div>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => navigate("/import")}
          className="flex items-center gap-2 rounded-lg bg-aurora-accent px-3 py-1.5 text-xs font-semibold text-white shadow-glow-accent transition-transform hover:-translate-y-0.5"
        >
          <Upload size={14} />
          Import
        </button>
      </div>
    </header>
  );
}
