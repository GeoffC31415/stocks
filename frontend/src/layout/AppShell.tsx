import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AuroraBackground } from "../components/AuroraBackground";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PreferencesContext } from "../state/usePreferences";
import { DRIP_DEFAULT } from "../lib/formatters";

export function AppShell() {
  const location = useLocation();
  const [dripThreshold, setDripThreshold] = useState(DRIP_DEFAULT);

  return (
    <PreferencesContext.Provider value={{ dripThreshold, setDripThreshold }}>
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
