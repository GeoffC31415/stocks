import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { LegacyRedirect } from "./routing";
const ActivityWorkspace = lazy(() => import("./routes/ActivityWorkspace").then(module => ({default: module.ActivityWorkspace})));
const CGT = lazy(() => import("./routes/CGT").then(module => ({default: module.CGT})));
const DataWorkspace = lazy(() => import("./routes/DataWorkspace").then(module => ({default: module.DataWorkspace})));
const Help = lazy(() => import("./routes/Help").then(module => ({default: module.Help})));
const Security = lazy(() => import("./auth/Security").then(module => ({default: module.Security})));
import { useAuth } from "./auth/AuthProvider";
const Overview = lazy(() => import("./routes/Overview").then(module => ({default: module.Overview})));
const PortfolioWorkspace = lazy(() => import("./routes/PortfolioWorkspace").then(module => ({default: module.PortfolioWorkspace})));

function SecurityRoute() {
  const { session } = useAuth();
  return session?.mode === "local" ? <Navigate to="/" replace /> : <Security />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><Overview /></Suspense>} />
          <Route path="/portfolio" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><PortfolioWorkspace /></Suspense>} />
          <Route path="/activity" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><ActivityWorkspace /></Suspense>} />
          <Route path="/tax" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><CGT /></Suspense>} />
          <Route path="/data" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><DataWorkspace /></Suspense>} />
          <Route path="/help" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><Help /></Suspense>} />
          <Route path="/security" element={<Suspense fallback={<div role="status" aria-label="Loading workspace" className="min-h-[560px] animate-pulse rounded-2xl bg-white/[0.02] p-5">Loading workspace…</div>}><SecurityRoute /></Suspense>} />

          <Route path="/holdings" element={<LegacyRedirect target="/portfolio" tab="holdings" />} />
          <Route path="/positions" element={<LegacyRedirect target="/portfolio" tab="returns" />} />
          <Route path="/groups" element={<LegacyRedirect target="/portfolio" tab="groups" />} />
          <Route path="/orders" element={<LegacyRedirect target="/activity" tab="orders" />} />
          <Route path="/diff" element={<LegacyRedirect target="/activity" tab="changes" />} />
          <Route path="/import" element={<LegacyRedirect target="/data" tab="import" />} />
          <Route path="/matching" element={<LegacyRedirect target="/data" tab="matching" />} />
          <Route path="/cgt" element={<LegacyRedirect target="/tax" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
