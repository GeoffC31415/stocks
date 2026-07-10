import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { ImportPage } from "./Import";
import { MatchingAdmin } from "./MatchingAdmin";

const TABS = [
  { key: "import", label: "Import & refresh" },
  { key: "matching", label: "Matching" },
];

export function DataWorkspace() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "import";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Data views" tabs={TABS} />
      {tab === "matching" ? <MatchingAdmin /> : <ImportPage />}
    </div>
  );
}
