import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { ClassificationQueue } from "../components/ClassificationQueue";
import { ImportPage } from "./Import";
import { MatchingWorkspace } from "./MatchingWorkspace";
import { AnalysisSettings } from "../components/AnalysisSettings";
import { DataConfidencePanel } from "../components/DataConfidencePanel";

const TABS = [
  { key: "import", label: "Import & refresh" },
  { key: "classifications", label: "Classifications" },
  { key: "matching", label: "Matching" },
  { key: "settings", label: "Analysis settings" },
  { key: "confidence", label: "Data confidence" },
];

export function DataWorkspace() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "import";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Data views" tabs={TABS} />
      {(tab === "matching" || tab === "classifications") && <p className="text-xs text-slate-400">This repair queue includes all accounts. Check the source account before changing a record.</p>}
      {tab === "confidence" ? <DataConfidencePanel /> : tab === "settings" ? <AnalysisSettings /> : tab === "matching" ? (
        <MatchingWorkspace />
      ) : tab === "classifications" ? (
        <ClassificationQueue />
      ) : (
        <ImportPage />
      )}
    </div>
  );
}
