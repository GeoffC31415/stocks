import { createContext, useContext, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

export const PERIODS = ["1M", "3M", "6M", "1Y", "YTD", "ALL"] as const;
export type AnalysisPeriod = typeof PERIODS[number];
type ScopeDefaults = { account: string; period: AnalysisPeriod };
export const isAnalysisPeriod = (value: string): value is AnalysisPeriod =>
  PERIODS.some((period) => period === value);

export function parseAnalysisScope(params: URLSearchParams, defaults: ScopeDefaults, accounts?: string[]) {
  const account = params.get("account") ?? defaults.account;
  const rawPeriod = params.get("period") ?? defaults.period;
  const errors: string[] = [];
  for (const key of ["account", "period", "start", "end"]) {
    if (params.getAll(key).length > 1) errors.push(`Repeated scope parameter: ${key}.`);
  }
  if (!account || /[\u0000-\u001f]/.test(account)) errors.push("Invalid account parameter.");
  else if (account !== "all" && accounts && !accounts.includes(account)) errors.push("Unknown account. Choose an available account.");
  if (!isAnalysisPeriod(rawPeriod)) errors.push("Invalid period. Choose 1M, 3M, 6M, 1Y, YTD or ALL.");
  const start = params.get("start"), end = params.get("end");
  for (const date of [start, end]) {
    if (date !== null && (!/^\d{4}-\d{2}-\d{2}$/.test(date) ||
      !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date)) {
      errors.push("Dates must be real calendar dates in YYYY-MM-DD format.");
    }
  }
  if (start && end && start > end) errors.push("Start date must not follow end date.");
  if (start !== null || end !== null) errors.push("Custom analysis dates are not supported. Choose a period instead.");
  return { account, period: isAnalysisPeriod(rawPeriod) ? rawPeriod : "ALL" as AnalysisPeriod, errors };
}

function storedDefaults(): ScopeDefaults {
  try {
    const period = localStorage.getItem("portfolio.analysisPeriod") ?? "ALL";
    return { account: localStorage.getItem("portfolio.accountFilter") ?? "all",
      period: isAnalysisPeriod(period) ? period : "ALL" };
  } catch { return { account: "all", period: "ALL" }; }
}

export function useAnalysisScopeUrl(accounts?: string[]) {
  const [params, setParams] = useSearchParams();
  const [defaults] = useState(storedDefaults);
  const scope = parseAnalysisScope(params, defaults, accounts);
  const valid = scope.errors.length === 0;
  // Materialise defaults once per unscoped location so Back never depends on
  // a subsequently changed storage value. Explicit URL values always win.
  useEffect(() => {
    if (!valid) return;
    if (!params.has("account") || !params.has("period")) {
      const next = new URLSearchParams(params);
      next.set("account", scope.account);
      next.set("period", scope.period);
      setParams(next, { replace: true });
    }
    try {
      localStorage.setItem("portfolio.accountFilter", scope.account);
      localStorage.setItem("portfolio.analysisPeriod", scope.period);
    } catch { /* Private browsing may disable preference storage. */ }
  }, [params, scope.account, scope.period, valid, setParams]);

  const update = (key: "account" | "period", value: string) => {
    const next = new URLSearchParams(params);
    if (!next.has("account")) next.set("account", scope.account);
    if (!next.has("period")) next.set("period", scope.period);
    next.set(key, value);
    setParams(next);
  };
  const reset = () => {
    const next = new URLSearchParams(params);
    for (const key of ["account", "period", "start", "end"]) next.delete(key);
    next.set("account", "all"); next.set("period", "ALL");
    setParams(next);
  };
  return { ...scope, setAccount: (value: string) => update("account", value),
    setPeriod: (value: AnalysisPeriod) => update("period", value), reset };
}

export const AnalysisScopeContext = createContext({
  period: "ALL" as AnalysisPeriod, setPeriod: (_value: AnalysisPeriod) => {},
});
export const useAnalysisScope = () => useContext(AnalysisScopeContext);
