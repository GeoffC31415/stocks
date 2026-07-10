import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { Diff } from "./Diff";
import { ImportActivity } from "./ImportActivity";
import { Orders } from "./Orders";

const TABS = [
  { key: "orders", label: "Orders" },
  { key: "changes", label: "Snapshot changes" },
  { key: "imports", label: "Import history" },
];

export function ActivityWorkspace() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "orders";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Activity views" tabs={TABS} />
      {tab === "changes" ? <Diff /> : tab === "imports" ? <ImportActivity /> : <Orders />}
    </div>
  );
}
