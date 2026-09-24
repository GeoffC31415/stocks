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
  it("public service request waits for the new run before invalidating", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    const request = vi.spyOn(api, "requestSync").mockResolvedValue({ state: "accepted", request_id: "new-run" });
    let finish!: (value: Awaited<ReturnType<typeof api.getRequestedSyncStatus>>) => void;
    vi.spyOn(api, "getRequestedSyncStatus").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync all accounts" }));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    await waitFor(() => expect(api.getRequestedSyncStatus).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: /Syncing all accounts/ })).toBeDisabled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Sync Trading 212" })).not.toBeInTheDocument();
    expect(screen.queryByText(/credentials to .env/)).not.toBeInTheDocument();
    finish({ state: "completed", request_id: "new-run", last_run: { started_at: "2026-09-23T12:00:00Z", finished_at: "2026-09-23T12:01:00Z", ok: true, steps: [], files: [] } });
    expect(await screen.findByText("Sync complete.")).toBeInTheDocument();
    await waitFor(() => expect(invalidate).toHaveBeenCalledOnce());
  });

  it.each(["failed", "unknown"] as const)("shows %s service outcomes", async (state) => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestSync").mockResolvedValue({ state: "accepted", request_id: "new-run" });
    vi.spyOn(api, "getRequestedSyncStatus").mockResolvedValue({ state, request_id: "new-run", last_run: null });
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync all accounts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(state === "failed" ? "Sync failed" : "unknown");
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("bounds pending even when a poll never returns", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.spyOn(api, "requestSync").mockResolvedValue({ state: "accepted", request_id: "new-run" });
    vi.spyOn(api, "getRequestedSyncStatus").mockImplementation(() => new Promise(() => {}));
    show();
    const button = await screen.findByRole("button", { name: "Sync all accounts" });
    vi.useFakeTimers();
    try {
      await act(async () => { fireEvent.click(button); await vi.advanceTimersByTimeAsync(50); });
      expect(screen.getByRole("button", { name: /Syncing all accounts/ })).toBeDisabled();
      await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60 * 1000 + 50); });
      expect(screen.getByRole("alert")).toHaveTextContent("unknown");
      expect(screen.getByRole("button", { name: "Sync all accounts" })).toBeEnabled();
    } finally { vi.useRealTimers(); }
  });

  it("keeps local sync immediate", async () => {
    const sync = vi.spyOn(api, "syncAll").mockResolvedValue({ started_at: "now", finished_at: "now", ok: true, steps: [{ name: "Barclays", status: "ok", detail: null }], files: [] });
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sync all accounts" }));
    await waitFor(() => expect(sync).toHaveBeenCalledWith(true));
    expect(await screen.findByText("Barclays: ok")).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalled();
  });

});
