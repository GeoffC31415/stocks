import type { MetricReason } from "../lib/api";

type Props = {
  title: string;
  reasons?: MetricReason[];
} & (
  | { kind: "error"; onRetry?: () => void }
  | { kind: "loading" | "empty" | "unavailable" | "warning"; onRetry?: never }
);

/** Keep fetch errors, missing observations and valid empty selections distinct. */
export function AnalysisStatus({ kind, title, reasons = [], onRetry }: Props) {
  return (
    <div role={kind === "error" ? "alert" : "status"}
      className="space-y-2 rounded-xl border border-slate-500/20 p-3 text-sm text-slate-300">
      <p className="font-medium">{title}</p>
      {reasons.length > 0 && <ul className="space-y-1">
        {reasons.map((reason) => <li key={`${reason.code}:${reason.message}`}>
          {reason.message}
          {reason.action_href && <a className="ml-2 underline focus-visible:outline" href={reason.action_href}>Investigate</a>}
        </li>)}
      </ul>}
      {kind === "error" && onRetry && <button type="button" onClick={onRetry}
        className="min-h-11 rounded-lg border border-white/20 px-4 focus-visible:outline">Retry</button>}
    </div>
  );
}
