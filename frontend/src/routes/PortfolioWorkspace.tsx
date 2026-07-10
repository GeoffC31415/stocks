import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { AllocationAnalysisPanel } from "../components/AllocationAnalysisPanel";
import { IncomeAnalysisPanel } from "../components/IncomeAnalysisPanel";
import { Groups } from "./Groups";
import { Holdings } from "./Holdings";
import { Positions } from "./Positions";

const TABS = [
  { key: "holdings", label: "Holdings" },
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
      {tab === "returns" ? (
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
