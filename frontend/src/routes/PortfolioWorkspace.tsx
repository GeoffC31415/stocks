import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { AllocationAnalysisPanel } from "../components/AllocationAnalysisPanel";
import { IncomeAnalysisPanel } from "../components/IncomeAnalysisPanel";
import { Groups } from "./Groups";
import { Holdings } from "./Holdings";
import { Positions } from "./Positions";
import { PerformanceWorkspace } from "./PerformanceWorkspace";

const TABS = [
  { key: "holdings", label: "Holdings" },
  { key: "performance", label: "Performance" },
  { key: "returns", label: "Returns" },
  { key: "allocation", label: "Allocation" },
  { key: "income", label: "Income" },
  { key: "groups", label: "Groups" },
];

export function PortfolioWorkspace() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "holdings";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Portfolio views" tabs={TABS} />
      <p className="text-xs text-slate-400">{tab === "performance" ? "Performance uses the shared period and disclosed covered valuation dates." : tab === "income"
        ? "Income uses a today-based trailing window, not the performance period. Recorded transactions do not prove complete dividend coverage."
        : tab === "returns" ? "Holding returns use recorded lifetime transactions and current values, not the performance period."
        : "Current holdings, allocation and groups use latest account snapshots, not the performance period."}</p>
      {tab === "performance" ? <PerformanceWorkspace /> : tab === "returns" ? (
        <Positions />
      ) : tab === "allocation" ? (
        <AllocationAnalysisPanel />
      ) : tab === "income" ? (
        <IncomeAnalysisPanel />
      ) : tab === "groups" ? (
        <Groups />
      ) : (
        <Holdings />
      )}
    </div>
  );
}
