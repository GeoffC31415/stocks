import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { api, type SnapshotAttribution } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { Diff } from "../Diff";

const from = { id: 4, as_of_date: "2026-01-01", created_at: "2026-01-02", file_sha256: "a", filename: null, diff_summary: null };
const to = { ...from, id: 5, as_of_date: "2026-02-01" };
const attribution: SnapshotAttribution = {
  from_batch: from, to_batch: to, opening_value_gbp: 100, closing_value_gbp: 120,
  raw_value_change_gbp: 20, contributions_gbp: 10, withdrawals_gbp: 0, drip_proxy_gbp: 0,
  net_external_flow_gbp: 10, residual_market_movement_gbp: 10, reconciliation_difference_gbp: 0,
  top_contributors: [], top_detractors: [], notes: ["Estimated, not proven price effects."],
  movements: [{ instrument_id: 7, identifier: "A", security_name: "Alpha", account_name: "ISA", opening_value_gbp: 100,
    closing_value_gbp: 120, raw_value_change_gbp: 20, net_external_flow_gbp: 10, drip_proxy_gbp: 0,
    estimated_market_movement_gbp: 10, contribution_pct_points: null, source_order_ids: [9] }],
  percentage_point_reason: "No validated percentage-point denominator.", unallocated_residual_gbp: 0,
};
function show(search: string) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/activity?tab=changes&${search}`]}>
      <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}><Diff /></PreferencesContext.Provider>
    </MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(api, "getImports").mockResolvedValue([to, from]);
  vi.spyOn(api, "getSnapshotAttribution").mockResolvedValue(attribution);
  vi.spyOn(api, "compareImports").mockResolvedValue({ from_batch: from, to_batch: to, rows: [] });
});
it("opens the exact comparison and selected contribution rather than another default period", async () => {
  show("account=ISA&period=YTD&from=4&to=5&inst=7");
  expect(await screen.findByRole("heading", { name: "Estimated contributions by holding" })).toBeInTheDocument();
  expect(api.getSnapshotAttribution).toHaveBeenCalledWith("ISA", 4, 5);
  await waitFor(() => expect(api.compareImports).toHaveBeenCalledWith(4, 5, "ISA"));
  expect(screen.getByText("Alpha")).toBeInTheDocument();
  expect(screen.getByText("No validated percentage-point denominator.")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Opening snapshot" })).toHaveValue("4");
});
it("rejects malformed identifiers without querying another comparison", () => {
  show("from=4e0&to=5");
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid comparison");
  expect(api.getSnapshotAttribution).not.toHaveBeenCalled();
  expect(api.compareImports).not.toHaveBeenCalled();
});
