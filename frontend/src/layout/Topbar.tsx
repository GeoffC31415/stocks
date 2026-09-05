import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Calendar, Settings2, Upload } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatOrderDate } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { isAnalysisPeriod, PERIODS, useAnalysisScope } from "../state/useAnalysisScope";
import { SegmentedControl, type Segment } from "../components/SegmentedControl";
import { scopedNavigationUrl } from "../routing";

export function Topbar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { accountFilter, setAccountFilter } = usePreferences();
  const { period, setPeriod } = useAnalysisScope();
  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.getSummary });
  const accountSegments: Segment<string>[] = useMemo(() => [
    { key: "all", label: "All" },
    ...Object.keys(summaryQ.data?.by_account ?? {}).sort().map((name) => ({ key: name, label: name })),
  ], [summaryQ.data?.by_account]);
  const asOf = accountFilter === "all" ? summaryQ.data?.as_of_date : null;
  const go = (target: string) => navigate(scopedNavigationUrl(target, location.search));

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.05] bg-aurora-base/60 px-3 py-3 backdrop-blur-xl sm:px-6">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <Calendar size={14} className="hidden text-slate-500 sm:block" />
        <span className="text-xs text-slate-400">
          {asOf ? `Latest snapshot across accounts · ${formatOrderDate(asOf)}` : "Valuation dates shown with analysis"}
        </span>
      </div>
      <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2 sm:gap-3">
        {accountSegments.length > 1 ? <>
          <label className="sr-only" htmlFor="mobile-account-filter">Account</label>
          <select id="mobile-account-filter" aria-label="Account" value={accountFilter}
            onChange={(event) => setAccountFilter(event.target.value)}
            className="max-w-36 rounded-lg border border-white/[0.08] bg-aurora-base/80 px-2 py-2 text-xs text-slate-200 md:hidden">
            {accountSegments.map((segment) => <option key={segment.key} value={segment.key}>{segment.label}</option>)}
          </select>
          <div className="hidden min-w-0 max-w-full md:block">
            <SegmentedControl layoutId="account-filter" value={accountFilter} onChange={setAccountFilter}
              tone="violet" size="sm" segments={accountSegments} />
          </div>
        </> : null}
        <label className="flex items-center gap-2 text-xs text-slate-300">
          Performance period
          <select aria-label="Performance period" value={period}
            onChange={(event) => { if (isAnalysisPeriod(event.target.value)) setPeriod(event.target.value); }}
            className="min-h-9 rounded-lg bg-aurora-base px-2 text-slate-200">
            {PERIODS.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button type="button" aria-label="Analysis settings" onClick={() => go("/data?tab=settings")}
          className="min-h-9 rounded-lg px-2 text-slate-300"><Settings2 size={16} /></button>
        <button type="button" aria-label="Refresh data" onClick={() => go("/data?tab=import")}
          className="flex min-h-9 items-center gap-2 rounded-lg bg-aurora-accent px-3 text-xs font-semibold text-white">
          <Upload size={14} /><span className="hidden sm:inline">Refresh data</span>
        </button>
      </div>
    </header>
  );
}
