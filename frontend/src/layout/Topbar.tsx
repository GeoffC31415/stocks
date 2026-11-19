import { useMemo } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, KeyRound, LogOut, RefreshCw, Settings2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { SyncEvidence, refreshOutcome } from "../components/SyncEvidence";
import { api } from "../lib/api";
import { formatOrderDate } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { isAnalysisPeriod, PERIODS, useAnalysisScope } from "../state/useAnalysisScope";
import { scopedNavigationUrl } from "../routing";
import { useAuth } from "../auth/AuthProvider";
import { PRIMARY_NAV } from "./Sidebar";

export function Topbar() {
  const navigate = useNavigate();
  const syncQ = useQuery({ queryKey: ["syncStatus"], queryFn: api.getSyncStatus, retry: false });
  const location = useLocation();
  const { accountFilter, setAccountFilter } = usePreferences();
  const { period, setPeriod } = useAnalysisScope();
  const { session, logout } = useAuth();
  const catalogQ = useQuery({ queryKey: ["summary", undefined], queryFn: () => api.getSummary() });
  const selectedAccount = accountFilter === "all" ? undefined : accountFilter;
  const summaryQ = useQuery({ queryKey: ["summary", selectedAccount], queryFn: () => api.getSummary(selectedAccount) });
  const accountOptions = useMemo(() => [
    { key: "all", label: "All" },
    ...Object.keys(catalogQ.data?.by_account ?? {}).sort().map((name) => ({ key: name, label: name })),
  ], [catalogQ.data?.by_account]);
  const dates = summaryQ.data?.scope?.valuation_dates.map((row) => row.date).sort() ?? [];
  const asOf = summaryQ.data?.as_of_date;
  const dateLabel = dates.length > 1 && dates[0] !== dates[dates.length - 1]
    ? `${formatOrderDate(dates[0])} – ${formatOrderDate(dates[dates.length - 1])}`
    : asOf ? formatOrderDate(asOf) : null;
  const go = (target: string) => navigate(scopedNavigationUrl(target, location.search));

  const report = syncQ.data?.last_run ?? syncQ.data;
  const outcome = refreshOutcome(report);
  const dotClass = syncQ.isError || outcome === "failed"
    ? "bg-rose-400"
    : outcome === "complete"
      ? "bg-emerald-400"
      : outcome === "partial"
        ? "bg-amber-400"
        : "bg-slate-500";

  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.09] bg-[#0a0c10]/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1560px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2 sm:px-5 lg:h-11 lg:flex-nowrap lg:px-6 lg:py-0">
        {/* Left: compact wordmark + inline primary navigation (reclaims 224px sidebar width) */}
        <div className="flex min-w-0 items-center gap-5">
          <span className="num text-xs font-semibold tracking-[0.16em] text-white">
            PORTFOLIO
          </span>
          <nav aria-label="Primary" className="hidden items-center gap-0.5 lg:flex">
            {PRIMARY_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={scopedNavigationUrl(item.to, location.search)}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `relative inline-flex h-11 items-center px-2.5 text-xs font-medium transition-colors ${
                    isActive
                      ? "text-white"
                      : "text-slate-400 hover:text-slate-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span>{item.label}</span>
                    {isActive ? (
                      <span
                        aria-hidden="true"
                        className="absolute inset-x-1.5 bottom-0 h-[1.5px] bg-sky-400"
                      />
                    ) : null}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Right: tight inline scope + telemetry + utilities */}
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2.5 lg:flex-nowrap">
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
            <span className="sr-only">
              {syncQ.data || syncQ.isError ? (
                <SyncEvidence report={report} compact unavailable={syncQ.isError} onRetry={() => void syncQ.refetch()} />
              ) : (
                "Checking…"
              )}
            </span>
            <span className="num text-slate-300">
              <span className="sr-only">Snapshot valuation </span>
              {dateLabel ?? (summaryQ.isError ? "Unavailable" : "—")}
            </span>
          </div>

          <span aria-hidden="true" className="hidden h-3.5 w-px bg-white/[0.1] sm:block" />

          {accountOptions.length > 1 ? (
            <>
              <label className="sr-only" htmlFor="mobile-account-filter">Account</label>
              <div className="relative md:hidden">
                <select
                  id="mobile-account-filter"
                  aria-label="Account"
                  value={accountFilter}
                  onChange={(event) => setAccountFilter(event.target.value)}
                  className="min-h-7 appearance-none rounded-sm border border-white/[0.1] bg-white/[0.03] py-0.5 pl-2 pr-6 text-[11px] font-medium text-slate-200"
                >
                  {accountOptions.map((opt) => (
                    <option key={opt.key} value={opt.key}>{opt.label}</option>
                  ))}
                </select>
                <ChevronDown size={11} aria-hidden="true" className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400" />
              </div>
              <div role="group" aria-label="Account filter" className="hidden items-center border border-white/[0.09] bg-white/[0.02] p-0.5 md:inline-flex">
                {accountOptions.map((opt) => {
                  const active = opt.key === accountFilter;
                  return (
                    <button
                      key={opt.key}
                      type="button"
                      aria-pressed={active}
                      onClick={() => setAccountFilter(opt.key)}
                      className={`px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        active
                          ? "bg-white/[0.12] text-white"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}

          <div className="relative flex items-center">
            <label className="sr-only" htmlFor="topbar-period-select">Performance period</label>
            <select
              id="topbar-period-select"
              aria-label="Performance period"
              value={period}
              onChange={(event) => {
                if (isAnalysisPeriod(event.target.value)) setPeriod(event.target.value);
              }}
              className="num min-h-7 appearance-none rounded-sm border border-white/[0.1] bg-white/[0.03] py-0.5 pl-2 pr-6 text-[11px] font-medium text-slate-200 hover:border-white/[0.2]"
            >
              {PERIODS.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <ChevronDown size={11} aria-hidden="true" className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400" />
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Refresh data"
              title="Refresh data"
              onClick={() => go("/data?tab=import")}
              className="btn-primary h-7 gap-1.5 px-2.5"
            >
              <RefreshCw size={11} />
              <span className="hidden sm:inline">Sync</span>
            </button>
            <button
              type="button"
              aria-label="Analysis settings"
              title="Analysis settings"
              onClick={() => go("/data?tab=settings")}
              className="inline-flex h-7 w-7 items-center justify-center rounded-sm text-slate-400 hover:bg-white/[0.06] hover:text-white"
            >
              <Settings2 size={13} />
            </button>
            {session?.mode !== "local" ? (
              <>
                <button
                  type="button"
                  aria-label="Passkey security"
                  title="Passkey security"
                  onClick={() => go("/security")}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-sm text-slate-400 hover:bg-white/[0.06] hover:text-white"
                >
                  <KeyRound size={13} />
                </button>
                <button
                  type="button"
                  aria-label="Log out"
                  title="Log out"
                  onClick={() => void logout()}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-sm text-slate-400 hover:bg-white/[0.06] hover:text-rose-300"
                >
                  <LogOut size={13} />
                </button>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
