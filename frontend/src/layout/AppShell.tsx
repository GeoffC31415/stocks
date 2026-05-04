import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AuroraBackground } from "../components/AuroraBackground";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PreferencesContext } from "../state/usePreferences";
import { DRIP_DEFAULT } from "../lib/formatters";

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
      <AuroraBackground />
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
            <div className="mx-auto max-w-[1400px]">
              <AnimatePresence mode="wait">
                <motion.div
                  key={location.pathname}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.22, ease: "easeOut" }}
                >
                  <Outlet />
                </motion.div>
              </AnimatePresence>
            </div>
          </main>
        </div>
      </div>
    </PreferencesContext.Provider>
  );
}
