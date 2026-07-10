import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { ClassificationQueue } from "../components/ClassificationQueue";
import { ImportPage } from "./Import";
import { MatchingWorkspace } from "./MatchingWorkspace";

const TABS = [
  { key: "import", label: "Import & refresh" },
  { key: "classifications", label: "Classifications" },
  { key: "matching", label: "Matching" },
];

export function DataWorkspace() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "import";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Data views" tabs={TABS} />
      {tab === "matching" ? (
        <MatchingWorkspace />
      ) : tab === "classifications" ? (
        <ClassificationQueue />
      ) : (
        <ImportPage />
      )}
    </div>
  );
}
