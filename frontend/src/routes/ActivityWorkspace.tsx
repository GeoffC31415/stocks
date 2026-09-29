import { useSearchParams } from "react-router-dom";
import { WorkspaceTabs } from "../components/WorkspaceTabs";
import { Diff } from "./Diff";
import { ImportActivity } from "./ImportActivity";
import { Orders } from "./Orders";
import { TimelineSourceView } from "./TimelineSourceView";

const TABS = [
  { key: "orders", label: "Orders" },
  { key: "changes", label: "Snapshot changes" },
  { key: "imports", label: "Import history" },
  { key: "source", label: "Source record" },
];

export function ActivityWorkspace() {
  const [params] = useSearchParams();
  const tab = TABS.some(t => t.key === params.get("tab")) ? params.get("tab")! : "orders";

  return (
    <div className="space-y-5">
      <WorkspaceTabs label="Activity views" tabs={TABS} />
      <div role="tabpanel" id="workspace-panel" aria-labelledby={`workspace-tab-${tab}`} tabIndex={0} className="space-y-5">
      <p className="text-xs text-slate-400">{tab === "source" ? "Read-only source record for the current account scope." : tab === "changes"
        ? "Latest snapshot comparison unless explicitly selected below; independent of the performance period."
        : tab === "imports" ? "Import history shows all recorded imports, independent of account and performance period."
        : "Transactions use their own date filters below, independent of the performance period."}</p>
      {tab === "source" ? <TimelineSourceView /> : tab === "changes" ? <Diff /> : tab === "imports" ? <ImportActivity /> : <Orders />}
      </div>
    </div>
  );
}
