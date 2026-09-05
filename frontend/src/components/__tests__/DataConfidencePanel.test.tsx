import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DataConfidencePanel } from "../DataConfidencePanel";
import { dataQualityApi, type DataConfidence } from "../../lib/dataQualityApi";
import { PreferencesContext } from "../../state/usePreferences";

const data: DataConfidence = {
  scope: { account_name: "ISA", requested_start: null, requested_end: null, effective_start: "2026-01-01", effective_end: "2026-02-01", valuation_dates: [], warnings: [] },
  evaluated_on: "2026-02-05", stale_after_days: 14, snapshots: [],
  transactions: { count: 7, first_date: "2026-01-01", last_date: "2026-02-01", unmatched_count: 0, review_count: 0, completeness: "unknown" },
  classification: {}, market_history: { covered_value_gbp: 0, non_cash_value_gbp: 100, covered_pct: 0,
    aligned_observations: 0, cache_gate_met: false, validation_pending: true, reasons: ["Provider validation pending."] },
  metric_reasons: [], attention: [],
};
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
      <DataConfidencePanel />
    </PreferencesContext.Provider>
  </QueryClientProvider>);
}
beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value) });
});
afterEach(() => vi.unstubAllGlobals());

it("discloses unknown transaction completeness and keeps unavailable proxy history separate from core checks", async () => {
  const request = vi.spyOn(dataQualityApi, "getConfidence").mockResolvedValue(data);
  show();
  expect(await screen.findByText("Core data checks healthy — view coverage and limitations")).toBeInTheDocument();
  expect(screen.getByText(/Completeness is unknown/)).toBeInTheDocument();
  expect(screen.getByText(/does not block snapshot or holdings analysis/)).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith("ISA", "ALL", 14);
  fireEvent.change(screen.getByRole("combobox", { name: "Snapshot freshness tolerance" }), { target: { value: "30" } });
  await waitFor(() => expect(request).toHaveBeenCalledWith("ISA", "ALL", 30));
});

it("never renders a failed check as healthy and offers retry", async () => {
  vi.spyOn(dataQualityApi, "getConfidence").mockRejectedValue(new Error("offline"));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to check data confidence.");
  expect(screen.queryByText(/Core data checks healthy/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});
