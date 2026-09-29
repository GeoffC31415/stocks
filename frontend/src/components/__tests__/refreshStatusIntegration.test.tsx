import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, type SyncRun } from "../../lib/api";
import { dataQualityApi, type DataConfidence } from "../../lib/dataQualityApi";
import { PreferencesContext } from "../../state/usePreferences";
import { Topbar } from "../../layout/Topbar";
import { DataConfidencePanel } from "../DataConfidencePanel";
import publicReport from "./fixtures/public-sync-v2.json";

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ session: { mode: "local" }, logout: vi.fn() }) }));
const summary = { as_of_date: "2026-09-01", import_batch_id: 5, total_value_gbp: 100, total_book_cost_gbp: 80,
  total_pnl_gbp: 20, by_account: { ISA: 100, Trading: 50 }, by_group: {}, allocation: [], group_allocation: [], worst_pct: [], best_pct: [] };
const confidence: DataConfidence = { scope: { account_name: "ISA", requested_start: null, requested_end: null,
  effective_start: "2026-01-01", effective_end: "2026-09-01", valuation_dates: [], warnings: [] },
  evaluated_on: "2026-09-29", stale_after_days: 14, snapshots: [], transactions: { count: 0, first_date: null,
    last_date: null, unmatched_count: 0, review_count: 0, completeness: "unknown" }, classification: {},
  market_history: { covered_value_gbp: 0, non_cash_value_gbp: 100, covered_pct: 0, aligned_observations: 0,
    cache_gate_met: false, validation_pending: true, reasons: [] }, metric_reasons: [], attention: [] };
function Surfaces() {
  const [accountFilter, setAccountFilter] = useState("ISA");
  return <PreferencesContext.Provider value={{ accountFilter, setAccountFilter, dripThreshold: 100, setDripThreshold: vi.fn() }}>
    <Topbar /><DataConfidencePanel />
  </PreferencesContext.Provider>;
}
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><Surfaces /></MemoryRouter></QueryClientProvider>);
  return client;
}
beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn() });
  vi.spyOn(api, "getSummary").mockResolvedValue(summary);
  vi.spyOn(api, "getSyncStatus").mockResolvedValue({ manual_sync_enabled: false, accounts: [], stale_after_days: 7,
    running: false, last_run: publicReport as SyncRun });
  vi.spyOn(dataQualityApi, "getConfidence").mockResolvedValue(confidence);
});

afterEach(() => vi.unstubAllGlobals());

it("shares an initial 503 failure and a read-only retry across both surfaces", async () => {
  vi.mocked(api.getSyncStatus).mockRejectedValue(new Error("503 Service Unavailable"));
  show();
  const panel = within(screen.getByRole("region", { name: "Data confidence" }));
  const header = within(screen.getByRole("banner"));
  for (const surface of [header, panel]) {
    expect(await surface.findByRole("alert")).toHaveTextContent("Refresh status unavailable.");
    expect(surface.queryByText(/Refresh outcome:/)).not.toBeInTheDocument();
    expect(surface.queryByText(/Cached refresh outcome:/)).not.toBeInTheDocument();
  }
  expect(screen.queryByText("Checking refresh…")).not.toBeInTheDocument();
  expect(api.getSyncStatus).toHaveBeenCalledTimes(1);
  vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, accounts: [], stale_after_days: 7,
    running: false, last_run: publicReport as SyncRun });
  fireEvent.click(panel.getByRole("button", { name: "Retry refresh status" }));
  expect(await header.findByText("Refresh outcome: partial")).toBeInTheDocument();
  expect(await panel.findByText("Checked: 2026-09-01T18:30:00+00:00")).toBeInTheDocument();
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
  expect(api.getSyncStatus).toHaveBeenCalledTimes(2);
});

it("keeps global cached refresh evidence qualified through account changes and failed retries", async () => {
  const client = show();
  const panel = within(screen.getByRole("region", { name: "Data confidence" }));
  const header = within(screen.getByRole("banner"));
  expect(await panel.findByText("Checked: 2026-09-01T18:30:00+00:00")).toBeInTheDocument();
  vi.mocked(api.getSyncStatus).mockRejectedValue(new Error("503 Service Unavailable"));
  await act(async () => { await client.refetchQueries({ queryKey: ["syncStatus"] }); });
  for (const account of ["Trading", "ISA", "all"]) {
    fireEvent.change(screen.getByRole("combobox", { name: "Account" }), { target: { value: account } });
    expect(await panel.findByText(/Core data checks healthy/)).toBeInTheDocument();
    expect(dataQualityApi.getConfidence).toHaveBeenCalledWith(account === "all" ? undefined : account, "ALL", 14);
    expect(header.getByText("Cached refresh outcome: partial")).toBeInTheDocument();
    expect(panel.getByRole("alert")).toHaveTextContent("current status is unknown");
    expect(panel.getByText("Checked: 2026-09-01T18:30:00+00:00")).toBeInTheDocument();
  }
  fireEvent.click(header.getByRole("button", { name: "Retry refresh status" }));
  expect(await panel.findByRole("alert")).toHaveTextContent("showing cached evidence");
  vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, accounts: [], stale_after_days: 7,
    running: false, last_run: { ...publicReport, outcome: "complete" } as SyncRun });
  await act(async () => { await client.refetchQueries({ queryKey: ["syncStatus"] }); });
  expect(await header.findByText("Refresh outcome: complete")).toBeInTheDocument();
  expect(panel.getByText("Refresh outcome: complete")).toBeInTheDocument();
  expect(screen.queryAllByRole("alert")).toHaveLength(0);
  expect(screen.queryByText("Cached refresh outcome: partial")).not.toBeInTheDocument();
});

it("qualifies retained refresh evidence after a failed read on both surfaces without losing timestamps", async () => {
  const client = show();
  const panel = within(screen.getByRole("region", { name: "Data confidence" }));
  expect(await panel.findByText("Checked: 2026-09-01T18:30:00+00:00")).toBeInTheDocument();
  vi.mocked(api.getSyncStatus).mockRejectedValue(new Error("503 Service Unavailable"));
  await act(async () => { await client.refetchQueries({ queryKey: ["syncStatus"] }); });
  const header = within(screen.getByRole("banner"));
  for (const surface of [header, panel]) {
    expect(await surface.findByRole("alert")).toHaveTextContent("Refresh status unavailable");
    expect(surface.getByText(/showing cached evidence; current status is unknown/)).toBeInTheDocument();
    expect(surface.getByText("Cached refresh outcome: partial")).toBeInTheDocument();
    expect(surface.queryByText("Refresh outcome: partial")).not.toBeInTheDocument();
    expect(surface.getByRole("button", { name: "Retry refresh status" })).toBeInTheDocument();
  }
  expect(panel.getByText("Checked: 2026-09-01T18:30:00+00:00")).toBeInTheDocument();
  expect(panel.getByText("Attempt: 2026-09-29T18:29:00+00:00")).toBeInTheDocument();
  expect(header.getByText(/Snapshot valuation/)).toBeInTheDocument();
});
