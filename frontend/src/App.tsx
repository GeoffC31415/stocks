import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { LegacyRedirect } from "./routing";
import { ActivityWorkspace } from "./routes/ActivityWorkspace";
import { CGT } from "./routes/CGT";
import { DataWorkspace } from "./routes/DataWorkspace";
import { Overview } from "./routes/Overview";
import { PortfolioWorkspace } from "./routes/PortfolioWorkspace";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Overview />} />
          <Route path="/portfolio" element={<PortfolioWorkspace />} />
          <Route path="/activity" element={<ActivityWorkspace />} />
          <Route path="/tax" element={<CGT />} />
          <Route path="/data" element={<DataWorkspace />} />

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
