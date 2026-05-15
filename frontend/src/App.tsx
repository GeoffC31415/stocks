import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { Overview } from "./routes/Overview";
import { Holdings } from "./routes/Holdings";
import { Orders } from "./routes/Orders";
import { Positions } from "./routes/Positions";
import { ImportPage } from "./routes/Import";
import { Groups } from "./routes/Groups";
import { Diff } from "./routes/Diff";
import { MatchingAdmin } from "./routes/MatchingAdmin";
import { CGT } from "./routes/CGT";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Overview />} />
          <Route path="/holdings" element={<Holdings />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/diff" element={<Diff />} />
          <Route path="/matching" element={<MatchingAdmin />} />
          <Route path="/cgt" element={<CGT />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
