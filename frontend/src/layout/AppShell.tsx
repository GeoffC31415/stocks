import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { AuroraBackground } from "../components/AuroraBackground";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { Topbar } from "./Topbar";
import { PreferencesContext } from "../state/usePreferences";
import { DRIP_DEFAULT } from "../lib/formatters";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { AnalysisScopeContext, useAnalysisScopeUrl } from "../state/useAnalysisScope";
import { useRouteFocus } from "../state/useRouteFocus";

const DRIP_STORAGE_KEY = "portfolio.dripThreshold";

const storedNumber = (key: string, fallback: number): number => {
  const raw = window.localStorage.getItem(key);
  if (raw == null) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};

export function AppShell() {
  const location = useLocation();
  const reducedMotion = useReducedMotion();
  const main = useRef<HTMLElement>(null);
  const routeKey = `${location.pathname}:${new URLSearchParams(location.search).get("tab") ?? ""}`;
  useRouteFocus(main, routeKey);
  const [dripThreshold, setDripThreshold] = useState(() =>
    storedNumber(DRIP_STORAGE_KEY, DRIP_DEFAULT),
  );
  const accountsQ = useQuery({ queryKey: ["summary"], queryFn: api.getSummary });
  const scope = useAnalysisScopeUrl(accountsQ.data ? Object.keys(accountsQ.data.by_account) : undefined);
  const accountFilter = scope.account;
  const setAccountFilter = scope.setAccount;

  useEffect(() => {
    window.localStorage.setItem(DRIP_STORAGE_KEY, String(dripThreshold));
  }, [dripThreshold]);

  return (
    <PreferencesContext.Provider
      value={{ dripThreshold, setDripThreshold, accountFilter, setAccountFilter }}
    >
      <AnalysisScopeContext.Provider value={scope}>
      <MotionConfig reducedMotion="user">
      <a href="#main-content" onClick={() => main.current?.focus()} className="skip-link">Skip to main content</a>
      <AuroraBackground />
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main id="main-content" ref={main} tabIndex={-1} className="flex-1 px-4 pb-24 pt-6 sm:px-6 lg:px-10 lg:py-8">
            <div className="mx-auto max-w-[1400px]">
              <motion.div data-testid="route-content" key={routeKey} initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }} transition={{ duration: reducedMotion ? 0 : 0.22 }}>
                {scope.errors.length > 0 ? (
                  <section role="alert" className="surface-card space-y-3 p-5">
                    <h1 className="text-lg font-semibold">Invalid analysis scope</h1>
                    {scope.errors.map((error) => <p key={error}>{error}</p>)}
                    <button type="button" className="btn-primary" onClick={scope.reset}>Reset account and period</button>
                  </section>
                ) : accountFilter !== "all" && !accountsQ.data ? (
                  <section role="status">
                    {accountsQ.isError ? <><p>Unable to validate the selected account. No analysis is shown.</p>
                      <button type="button" onClick={() => void accountsQ.refetch()}>Retry</button></>
                      : <p>Checking selected account…</p>}
                  </section>
                ) : <Outlet />}
              </motion.div>
            </div>
          </main>
        </div>
        <MobileNav />
      </div>
      </MotionConfig>
      </AnalysisScopeContext.Provider>
    </PreferencesContext.Provider>
  );
}
