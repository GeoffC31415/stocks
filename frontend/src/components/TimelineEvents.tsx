import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTimeline } from "../state/useTimeline";
import { groupTimelineEvents, parseEventKinds, TIMELINE_KINDS } from "../lib/timelineApi";
import { formatOrderDate } from "../lib/formatters";
import { scopedNavigationUrl } from "../routing";
import { AnalysisStatus } from "./AnalysisStatus";

export function TimelineEvents({ instrumentId }: { instrumentId?: number }) {
  const query = useTimeline(instrumentId);
  const [params, setParams] = useSearchParams();
  const selectedDate = params.get("eventDate");
  const kinds = parseEventKinds(params.get("eventKinds"));
  const [visibleDays, setVisibleDays] = useState(12);
  const groups = groupTimelineEvents((query.data?.events ?? []).filter((event) => kinds.includes(event.kind)));
  useEffect(() => {
    if (!selectedDate) return;
    const index = groups.findIndex((group) => group.date === selectedDate);
    if (index < 0) return;
    setVisibleDays((count) => Math.max(count, index + 1));
    const frame = requestAnimationFrame(() => {
      if (document.activeElement?.matches("input, select, textarea")) return;
      const target = document.getElementById(`timeline-day-${selectedDate}`);
      target?.focus({ preventScroll: true }); target?.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedDate, query.data]); // Groups are display-only; the response and URL identify the selected day.
  const toggleKind = (kind: typeof kinds[number]) => {
    const next = new URLSearchParams(params);
    next.set("eventKinds", (kinds.includes(kind) ? kinds.filter((value) => value !== kind) : [...kinds, kind]).join(","));
    setParams(next);
  };
  return <section className="surface-card min-w-0 space-y-3 p-4 [overflow-wrap:anywhere] sm:p-5" aria-label="Timeline events">
    <h2 className="text-base font-semibold">Timeline events</h2>
    {query.isLoading ? <p role="status">Loading recorded events…</p> : query.isError
      ? <AnalysisStatus kind="error" title="Unable to load timeline events." onRetry={() => void query.refetch()} />
      : query.data && <>
        <p className="text-xs text-slate-400">{query.data.event_count} source-backed events in the covered valuation window.
          Select a numbered chart marker to open its date. Markers group by day; up to 12 dates are marked to avoid clutter. Every event remains available here.</p>
        <fieldset className="flex flex-wrap gap-x-4 gap-y-2"><legend className="mb-2 text-xs text-slate-400">Event categories</legend>
          {TIMELINE_KINDS.map(({ key, label }) => <label key={key} className="flex min-h-9 items-center gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={kinds.includes(key)} onChange={() => toggleKind(key)} />{label} ({query.data?.counts_by_kind[key] ?? 0})
          </label>)}
        </fieldset>
        <div className="space-y-1">{query.data.notes.map((note) => <p key={note} className="text-xs text-slate-400">{note}</p>)}</div>
        {groups.length === 0 && <p className="text-sm text-slate-300">No recorded events for the selected categories in this covered window.</p>}
        {groups.slice(0, visibleDays).map((group) => <details key={group.date} open={selectedDate === group.date} className="border-t border-white/5 pt-2">
          <summary id={`timeline-day-${group.date}`} className="min-h-9 cursor-pointer text-sm text-slate-200" onClick={(event) => {
            event.preventDefault(); const next = new URLSearchParams(params);
            if (selectedDate === group.date) next.delete("eventDate"); else next.set("eventDate", group.date);
            setParams(next);
          }}>{formatOrderDate(group.date)} · {group.events.length} event{group.events.length === 1 ? "" : "s"}</summary>
          {selectedDate === group.date && <ul className="space-y-3 pb-3">{group.events.map((event) => <li key={event.id} className="text-xs text-slate-400">
            <p className="text-sm text-slate-200">{event.title}</p><p>{event.note}</p>
            <Link className="inline-flex min-h-9 items-center text-cyan-200 underline" to={scopedNavigationUrl(event.source_href, params.toString())}>View source {event.source_type} #{event.source_id}</Link>
          </li>)}</ul>}
        </details>)}
        {groups.length > visibleDays && <button type="button" className="min-h-10 text-sm text-cyan-200 underline" onClick={() => setVisibleDays((count) => count + 12)}>Show more dates ({groups.length - visibleDays} remaining)</button>}
      </>}
  </section>;
}
