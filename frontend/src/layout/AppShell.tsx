import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { AuroraBackground } from "../components/AuroraBackground";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { Topbar } from "./Topbar";
import { PreferencesContext } from "../state/usePreferences";
import { DRIP_DEFAULT } from "../lib/formatters";
import { useRouteFocus } from "../state/useRouteFocus";

const DRIP_STORAGE_KEY = "portfolio.dripThreshold";
const ACCOUNT_FILTER_STORAGE_KEY = "portfolio.accountFilter";

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
  const [accountFilter, setAccountFilter] = useState(
    () => window.localStorage.getItem(ACCOUNT_FILTER_STORAGE_KEY) ?? "all",
  );

  useEffect(() => {
    window.localStorage.setItem(DRIP_STORAGE_KEY, String(dripThreshold));
  }, [dripThreshold]);

  useEffect(() => {
    window.localStorage.setItem(ACCOUNT_FILTER_STORAGE_KEY, accountFilter);
  }, [accountFilter]);

  return (
    <PreferencesContext.Provider
      value={{ dripThreshold, setDripThreshold, accountFilter, setAccountFilter }}
    >
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
                <Outlet />
              </motion.div>
            </div>
          </main>
        </div>
        <MobileNav />
      </div>
      </MotionConfig>
    </PreferencesContext.Provider>
  );
}
