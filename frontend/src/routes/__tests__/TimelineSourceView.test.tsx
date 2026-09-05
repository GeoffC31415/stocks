import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { timelineApi } from "../../lib/timelineApi";
import { PreferencesContext } from "../../state/usePreferences";
import { TimelineSourceView } from "../TimelineSourceView";

function show(record: string) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/activity?tab=source&source=import&record=${record}&account=ISA&period=YTD&inst=7`]}>
      <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
        <TimelineSourceView />
      </PreferencesContext.Provider>
    </MemoryRouter></QueryClientProvider>);
}
beforeEach(() => vi.clearAllMocks());
it("shows the exact read-only source with distinct import and valuation dates", async () => {
  const getSource = vi.spyOn(timelineApi, "getSource").mockResolvedValue({ id: "import:2", kind: "import", date: "2026-01-10",
    occurred_at: "2026-01-10T12:00:00", valuation_date: "2026-01-01", account_names: ["ISA"], instrument_id: null,
    title: "Snapshot file imported", amount_gbp: null, source_type: "import", source_id: 2, source_href: "",
    details: { Filename: "synthetic.csv" }, note: "Administrative event, not a transaction." });
  show("2");
  expect(await screen.findByText("synthetic.csv")).toBeInTheDocument();
  expect(screen.getByText("2026-01-10T12:00:00")).toBeInTheDocument();
  expect(screen.getByText("2026-01-01")).toBeInTheDocument();
  expect(getSource).toHaveBeenCalledWith("import", 2, "ISA");
  expect(screen.getByRole("link", { name: "Back to investigation" })).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&inst=7&tab=holdings&events=on");
});
it.each(["2e0", "2&record=3", "2&source=order"])("rejects malformed or ambiguous source IDs: %s", (record) => {
  const request = vi.spyOn(timelineApi, "getSource");
  show(record);
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid source type or record identifier.");
  expect(request).not.toHaveBeenCalled();
});
