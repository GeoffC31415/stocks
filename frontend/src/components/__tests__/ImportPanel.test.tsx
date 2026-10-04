import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { ImportPanel } from "../ImportPanel";

function show() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <PreferencesContext.Provider
        value={{
          dripThreshold: 1000,
          setDripThreshold: vi.fn(),
          accountFilter: "all",
          setAccountFilter: vi.fn(),
        }}
      >
        <ImportPanel />
      </PreferencesContext.Provider>
    </QueryClientProvider>,
  );
}

describe("ImportPanel Trading 212 sync", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getSyncStatus").mockResolvedValue({ manual_sync_enabled: true, service_trigger_enabled: false, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "getTrading212Status").mockResolvedValue({
      configured: true,
      account_name: "Trading 212",
    });
    vi.spyOn(api, "syncTrading212Portfolio").mockResolvedValue({
      batch: {
        id: 1,
        created_at: "2026-09-07T12:00:00Z",
        as_of_date: "2026-09-07",
        file_sha256: "hash",
        filename: "trading212-api-portfolio.json",
        diff_summary: null,
      },
      summary: { row_count: 2 },
    });
    vi.spyOn(api, "syncTrading212Orders").mockResolvedValue({
      id: 1,
      created_at: "2026-09-07T12:00:00Z",
      filename: "trading212-api-orders.json",
      row_count: 1,
    });
  });

  it.each([false, true])("offers only Trading 212 sync (public service: %s)", async (publicService) => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: !publicService, service_trigger_enabled: publicService, accounts: [], stale_after_days: 7, last_run: null, running: false });
    show();
    expect(await screen.findByRole("button", { name: "Sync Trading 212" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Sync all accounts/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sync all accounts" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Downloads the latest Hargreaves/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Syncs automatically on weekdays/)).not.toBeInTheDocument();
  });

  it("syncs external cash flows separately and refreshes Dashboard data", async () => {
    const sync = vi.spyOn(api, "syncTrading212").mockResolvedValue({
      account_name: "Trading 212", snapshot: "imported", snapshot_rows: 2,
      orders: "imported", order_rows: 1, cash_flows_imported: 4, cash_flows_total: 4,
      fetched_at: "2026-09-09T12:00:00Z",
    });
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    const button = await screen.findByRole("button", { name: "Sync Trading 212" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(sync).toHaveBeenCalledOnce());
    expect(await screen.findByText(/cash: 4 new \/ 4 total/)).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalled();
  });
  it("public Trading 212 sync waits for its isolated service report without calling broker endpoints", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.mocked(api.getTrading212Status).mockResolvedValue({ configured: false, account_name: "Trading 212" });
    const direct = vi.spyOn(api, "syncTrading212");
    const all = vi.spyOn(api, "requestSync");
    const request = vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "accepted", request_id: "t212-run" });
    let finish!: (value: Awaited<ReturnType<typeof api.getRequestedTrading212SyncStatus>>) => void;
    vi.spyOn(api, "getRequestedTrading212SyncStatus").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    const button = await screen.findByRole("button", { name: "Sync Trading 212" });
    expect(button).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Force re-import/ }));
    fireEvent.click(button);
    await waitFor(() => expect(api.getRequestedTrading212SyncStatus).toHaveBeenCalledOnce());
    expect(request.mock.calls).toEqual([[]]);
    expect(screen.getByRole("button", { name: "Syncing Trading 212…" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalled();
    expect(direct).not.toHaveBeenCalled();
    expect(all).not.toHaveBeenCalled();
    expect(api.syncTrading212Portfolio).not.toHaveBeenCalled();
    expect(api.syncTrading212Orders).not.toHaveBeenCalled();
    expect(screen.queryByText(/credentials to .env/)).not.toBeInTheDocument();
    finish({ state: "completed", request_id: "t212-run", last_run: { started_at: "2026-09-23T12:00:00Z", finished_at: "2026-09-23T12:01:00Z", ok: true, steps: [], files: [], outcome: "partial" } });
    expect(await screen.findByText("Refresh outcome: partial")).toBeInTheDocument();
    await waitFor(() => expect(invalidate).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: "Sync Trading 212" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
  });

  it("reports a busy Trading 212 service without claiming acceptance or completion", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "busy", request_id: null });
    const poll = vi.spyOn(api, "getRequestedTrading212SyncStatus");
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync Trading 212" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another sync is already running");
    expect(poll).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.queryByText(/Trading 212 request accepted/)).not.toBeInTheDocument();
  });

  it("does not claim a trackable request when the Trading 212 service omits its request ID", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "accepted", request_id: null });
    const poll = vi.spyOn(api, "getRequestedTrading212SyncStatus");
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync Trading 212" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown");
    expect(poll).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sync Trading 212" })).toBeEnabled();
  });

  it("clears the prior Trading 212 result while a new request is pending or unconfirmed", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    let reject!: (error: Error) => void;
    vi.spyOn(api, "requestTrading212Sync")
      .mockResolvedValueOnce({ state: "accepted", request_id: "first-run" })
      .mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    vi.spyOn(api, "getRequestedTrading212SyncStatus").mockResolvedValue({ state: "completed", request_id: "first-run", last_run: { started_at: "now", finished_at: "now", ok: true, steps: [], files: [], outcome: "complete" } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync Trading 212" }));
    expect(await screen.findByText("Refresh outcome: complete")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sync Trading 212" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Syncing Trading 212…" })).toBeDisabled());
    expect(screen.queryByText("Refresh outcome: complete")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
    reject(new Error("Request disconnected"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not confirm the Trading 212 sync request");
    expect(screen.queryByText("Refresh outcome: complete")).not.toBeInTheDocument();
  });

  it.each([
    ["completed", "older-run", null, false],
    ["completed", null, null, false],
    ["failed", "t212-run", null, false],
    ["failed", "t212-run", "finished", true],
    ["unknown", "t212-run", null, false],
    ["disabled", "t212-run", null, false],
    ["inactive", "t212-run", null, false],
    ["busy", "t212-run", null, false],
  ] as const)("handles Trading 212 poll %s (%s, %s) without invalidating unrelated reports", async (state, request_id, finished_at, refresh) => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "accepted", request_id: "t212-run" });
    vi.spyOn(api, "getRequestedTrading212SyncStatus").mockResolvedValue({ state, request_id, last_run: finished_at ? { started_at: "now", finished_at, ok: false, steps: [], files: [], outcome: "failed" } : null });
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync Trading 212" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(request_id !== "t212-run" ? "unknown" : state === "failed" ? "failed" : state === "busy" ? "already running" : "unavailable");
    expect(invalidate).toHaveBeenCalledTimes(refresh ? 1 : 0);
    if (refresh) expect(screen.getByText("Refresh outcome: failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync Trading 212" })).toBeEnabled();
    expect(screen.queryByText("Refresh outcome: complete")).not.toBeInTheDocument();
  });

  it("reports unknown on Trading 212 poll errors without refreshing portfolio data", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "accepted", request_id: "t212-run" });
    vi.spyOn(api, "getRequestedTrading212SyncStatus").mockRejectedValue(new Error("Poll disconnected"));
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync Trading 212" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown");
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("bounds Trading 212 pending to 20 minutes and ignores late completion", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestTrading212Sync").mockResolvedValue({ state: "accepted", request_id: "t212-run" });
    let finish!: (value: Awaited<ReturnType<typeof api.getRequestedTrading212SyncStatus>>) => void;
    vi.spyOn(api, "getRequestedTrading212SyncStatus").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    const button = await screen.findByRole("button", { name: "Sync Trading 212" });
    vi.useFakeTimers();
    try {
      await act(async () => { fireEvent.click(button); await vi.advanceTimersByTimeAsync(50); });
      expect(screen.getByRole("button", { name: "Syncing Trading 212…" })).toBeDisabled();
      expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(19 * 60 * 1000); });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(60 * 1000 + 50); });
      expect(screen.getByRole("alert")).toHaveTextContent("unknown");
      expect(screen.getByRole("button", { name: "Sync Trading 212" })).toBeEnabled();
      expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
      await act(async () => {
        finish({ state: "completed", request_id: "t212-run", last_run: { started_at: "now", finished_at: "now", ok: true, steps: [], files: [], outcome: "complete" } });
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByRole("alert")).toHaveTextContent("unknown");
      expect(invalidate).not.toHaveBeenCalled();
    } finally { vi.useRealTimers(); }
  });


  it("hides Trading 212 when neither local nor service sync is enabled", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: false, accounts: [], stale_after_days: 7, last_run: null, running: false });
    show();
    await waitFor(() => expect(api.getSyncStatus).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Sync Trading 212" })).not.toBeInTheDocument();
  });

  it.each([false, true])("disables Trading 212 when another backend sync is running (public=%s)", async publicMode => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: !publicMode, service_trigger_enabled: publicMode, accounts: [], stale_after_days: 7, last_run: null, running: true });
    show();
    expect(await screen.findByRole("button", { name: "Sync Trading 212" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Syncing all accounts…" })).not.toBeInTheDocument();
  });


});
