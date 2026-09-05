import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { timelineApi, type TimelineEvent, type TimelineResponse } from "../../lib/timelineApi";
import { TimelineEvents } from "../TimelineEvents";
import { TimelineMarkerLabel } from "../TimelineMarkerLabel";
import { PreferencesContext } from "../../state/usePreferences";
import { AnalysisScopeContext } from "../../state/useAnalysisScope";

const events: TimelineEvent[] = [1, 2, 3].map((id) => ({ id: `${id === 3 ? "snapshot" : "order"}:${id}`, kind: id === 3 ? "snapshot" : "trade", date: "2026-01-10",
  occurred_at: id === 3 ? null : "2026-01-10T10:00:00", valuation_date: id === 3 ? "2026-01-10" : null, account_names: ["ISA"], instrument_id: 7,
  title: `Recorded event ${id}`, amount_gbp: id === 3 ? null : 10, source_type: id === 3 ? "import" : "order", source_id: id,
  source_href: `/activity?tab=source&source=${id === 3 ? "import" : "order"}&record=${id}&account=ISA&period=YTD`, details: {}, note: "Context, not causation." }));
const data: TimelineResponse = { scope: { account_name: "ISA", requested_start: null, requested_end: null,
  effective_start: "2026-01-01", effective_end: "2026-02-01", valuation_dates: [], warnings: [] },
  events, event_count: 3, counts_by_kind: { trade: 2, snapshot: 1 }, notes: ["Import time is separate from valuation time."] };
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/portfolio?tab=holdings&account=ISA&period=YTD&inst=7"]}>
      <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
        <AnalysisScopeContext.Provider value={{ period: "YTD", setPeriod: vi.fn() }}><TimelineEvents instrumentId={7} /></AnalysisScopeContext.Provider>
      </PreferencesContext.Provider>
    </MemoryRouter></QueryClientProvider>);
}
beforeEach(() => vi.clearAllMocks());
it("groups same-day records, toggles categories and preserves context in source links", async () => {
  const request = vi.spyOn(timelineApi, "getTimeline").mockResolvedValue(data);
  show();
  fireEvent.click(await screen.findByText("10 Jan 2026 · 3 events"));
  expect(screen.getAllByRole("link")).toHaveLength(3);
  expect(screen.getByRole("link", { name: "View source order #1" })).toHaveAttribute("href", "/activity?account=ISA&period=YTD&inst=7&eventDate=2026-01-10&tab=source&source=order&record=1");
  expect(request).toHaveBeenCalledWith("ISA", "YTD", 7);
  fireEvent.click(screen.getByRole("checkbox", { name: "Trades (2)" }));
  expect(screen.getByText("10 Jan 2026 · 1 event")).toBeInTheDocument();
  expect(screen.getAllByRole("link")).toHaveLength(1);
});
it("reports failed event loading instead of a zero event count", async () => {
  vi.spyOn(timelineApi, "getTimeline").mockRejectedValue(new Error("offline"));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load timeline events.");
  expect(screen.queryByText(/0 source-backed events/)).not.toBeInTheDocument();
});
it("provides a keyboard-operable chart marker with a dated accessible name", () => {
  const select = vi.fn();
  render(<svg><TimelineMarkerLabel viewBox={{ x: 100, y: 56 }} date="2026-01-10" count={3} number={1} width={320} onSelect={select} /></svg>);
  const marker = screen.getByRole("button", { name: "Timeline events on 2026-01-10: 3" });
  fireEvent.keyDown(marker, { key: "Enter" });
  fireEvent.keyDown(marker, { key: " " });
  expect(select).toHaveBeenCalledTimes(2);
  expect(select).toHaveBeenLastCalledWith("2026-01-10");
});
