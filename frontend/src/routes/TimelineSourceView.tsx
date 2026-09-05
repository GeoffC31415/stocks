import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { timelineApi, type TimelineSourceType } from "../lib/timelineApi";
import { toGbp } from "../lib/formatters";
import { usePreferences } from "../state/usePreferences";
import { scopedNavigationUrl } from "../routing";
import { AnalysisStatus } from "../components/AnalysisStatus";

export function TimelineSourceView() {
  const [params] = useSearchParams();
  const source = params.get("source");
  const rawId = params.get("record") ?? "";
  const valid = params.getAll("source").length === 1 && params.getAll("record").length === 1
    && (source === "order" || source === "import" || source === "order-import") && /^[1-9]\d*$/.test(rawId) && Number.isSafeInteger(Number(rawId));
  const { accountFilter } = usePreferences();
  const account = accountFilter === "all" ? undefined : accountFilter;
  const query = useQuery({ queryKey: ["timeline-source", source, rawId, account],
    queryFn: () => timelineApi.getSource(source as TimelineSourceType, Number(rawId), account), enabled: valid });
  const backParams = new URLSearchParams(params);
  backParams.delete("source"); backParams.delete("record");
  const back = scopedNavigationUrl(params.has("inst") ? "/portfolio?tab=holdings&events=on" : "/portfolio?tab=performance&events=on", backParams.toString());
  return <section className="surface-card min-w-0 space-y-4 p-4 [overflow-wrap:anywhere] sm:p-5">
    <h1 className="text-2xl font-semibold">Source record</h1>
    <p className="text-sm text-slate-400">Read-only evidence from an imported record. No orders or portfolio changes are created here.</p>
    {!valid ? <AnalysisStatus kind="error" title="Invalid source type or record identifier." />
      : query.isLoading ? <p role="status">Loading source record…</p>
      : query.isError ? <AnalysisStatus kind="error" title="Source record is unavailable in this account scope." onRetry={() => void query.refetch()} />
      : query.data && <>
        <h2 className="text-lg font-semibold">{query.data.title}</h2>
        <p className="text-sm text-slate-300">{query.data.source_type} #{query.data.source_id} · {query.data.account_names.join(" · ")}</p>
        <dl className="grid gap-x-5 gap-y-3 text-sm sm:grid-cols-[auto_minmax(0,1fr)]">
          <dt className="text-slate-400">Recorded timestamp</dt><dd>{query.data.occurred_at ?? "Not recorded"}</dd>
          {query.data.valuation_date && <><dt className="text-slate-400">Valuation date (separate from import time)</dt><dd>{query.data.valuation_date}</dd></>}
          {query.data.source_type === "order" && <><dt className="text-slate-400">Recorded amount</dt><dd>{query.data.amount_gbp == null ? "Unavailable (missing or invalid amount)" : toGbp(query.data.amount_gbp)}</dd></>}
          {Object.entries(query.data.details).map(([label, value]) => <div key={label} className="contents"><dt className="text-slate-400">{label}</dt><dd>{value ?? "Not recorded"}</dd></div>)}
        </dl>
        <p className="text-sm text-slate-400">{query.data.note}</p>
      </>}
    <Link className="inline-flex min-h-10 items-center text-sm text-cyan-200 underline" to={back}>Back to investigation</Link>
  </section>;
}
