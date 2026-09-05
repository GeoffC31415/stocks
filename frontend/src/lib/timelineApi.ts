import { requestJson, type AnalysisScope } from "./api";

export type TimelineSourceType = "order" | "import" | "order-import";
export type TimelineKind = "trade" | "deposit" | "withdrawal" | "transaction" | "snapshot" | "import";
export type TimelineEvent = {
  id: string; kind: TimelineKind; date: string; occurred_at: string | null; valuation_date: string | null;
  account_names: string[]; instrument_id: number | null; title: string; amount_gbp: number | null;
  source_type: TimelineSourceType; source_id: number; source_href: string;
  details: Record<string, string | null>; note: string;
};
export type TimelineResponse = { scope: AnalysisScope; events: TimelineEvent[]; event_count: number;
  counts_by_kind: Partial<Record<TimelineKind, number>>; notes: string[] };
export const timelineApi = {
  getTimeline: (account: string | undefined, period: string, instrumentId?: number) => {
    const params = new URLSearchParams({ period });
    if (account != null) params.set("account_name", account);
    if (instrumentId != null) params.set("instrument_id", String(instrumentId));
    return requestJson<TimelineResponse>(`/api/portfolio/timeline?${params}`);
  },
  getSource: (source: TimelineSourceType, id: number, account?: string) => {
    const params = new URLSearchParams();
    if (account != null) params.set("account_name", account);
    return requestJson<TimelineEvent>(`/api/portfolio/timeline/source/${source}/${id}?${params}`);
  },
};
export const TIMELINE_KINDS: Array<{ key: TimelineKind; label: string }> = [
  { key: "trade", label: "Trades" }, { key: "deposit", label: "Recorded deposits" },
  { key: "withdrawal", label: "Recorded withdrawals" }, { key: "transaction", label: "Other transactions" },
  { key: "snapshot", label: "Valuations" }, { key: "import", label: "Import times" },
];
export const DEFAULT_EVENT_KINDS: TimelineKind[] = ["trade", "snapshot"];
export function parseEventKinds(value: string | null): TimelineKind[] {
  if (value == null) return DEFAULT_EVENT_KINDS;
  return TIMELINE_KINDS.filter(({ key }) => value.split(",").includes(key)).map(({ key }) => key);
}
export function groupTimelineEvents(events: TimelineEvent[]): Array<{ date: string; events: TimelineEvent[] }> {
  const days = new Map<string, TimelineEvent[]>();
  for (const event of events) {
    const rows = days.get(event.date) ?? [];
    rows.push(event); days.set(event.date, rows);
  }
  return [...days].sort(([a], [b]) => a.localeCompare(b)).map(([date, records]) => ({ date, events: records }));
}
