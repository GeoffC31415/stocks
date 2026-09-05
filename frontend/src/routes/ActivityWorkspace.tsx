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
      <p className="text-xs text-slate-400">{tab === "changes"
        ? "Latest snapshot comparison unless explicitly selected below; independent of the performance period."
        : tab === "imports" ? "Import history shows all recorded imports, independent of account and performance period."
        : "Transactions use their own date filters below, independent of the performance period."}</p>
      {tab === "changes" ? <Diff /> : tab === "imports" ? <ImportActivity /> : <Orders />}
    </div>
  );
}
