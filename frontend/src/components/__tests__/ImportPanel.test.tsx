import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    vi.spyOn(api, "syncAll").mockImplementation(() => Promise.reject(new Error("unexpected combined sync")));
    vi.spyOn(api, "requestSync").mockImplementation(() => Promise.reject(new Error("unexpected service sync")));
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
    expect(sync).toHaveBeenCalledWith(false);
    expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import Barclays XLS snapshot" })).toBeInTheDocument();
    expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
    expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalled();
  });

  it("offers a direct Trading 212 refresh with legacy sync controls disabled", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: false, accounts: [], stale_after_days: 7, last_run: null, running: false });
    const sync = vi.spyOn(api, "syncTrading212").mockResolvedValue({
      account_name: "Trading 212", snapshot: "unchanged", snapshot_rows: null,
      orders: "unchanged", order_rows: null, cash_flows_imported: 0, cash_flows_total: 4,
      fetched_at: "2026-09-09T12:00:00Z",
    });
    show();
    const button = await screen.findByRole("button", { name: "Sync Trading 212" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(sync).toHaveBeenCalledWith(false));
    expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
    expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
  });

  it("requests the isolated worker without web broker credentials and polls to completion", async () => {
    vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
    vi.mocked(api.getTrading212Status).mockResolvedValue({ configured: false, account_name: "Trading 212" });
    const direct = vi.spyOn(api, "syncTrading212");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      expect(String(url)).toBe("/api/sync/trading212/request");
      return new Response(JSON.stringify(options?.method === "POST"
        ? { state: "accepted", request_id: "synthetic-request" }
        : { state: "completed", request_id: "synthetic-request", last_run: null }), { status: 200 });
    });
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    show();
    const button = await screen.findByRole("button", { name: "Sync Trading 212" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByText(/credentials to .env/)).not.toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1));
    await waitFor(() => expect(fetch.mock.calls.some(([, options]) => options?.method !== "POST")).toBe(true));
    expect(fetch.mock.calls[0][1]?.method).toBe("POST");
    expect(fetch.mock.calls[0][1]?.body).toBeUndefined();
    await waitFor(() => expect(button).toBeEnabled());
    expect(direct).not.toHaveBeenCalled();
    expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
    expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Import Barclays XLS snapshot" })).toBeInTheDocument();
  });

  it("keeps the Barclays XLS import as a manual upload", async () => {
    const file = new File(["portfolio"], "portfolio.xls");
    const importXls = vi.spyOn(api, "importXls").mockResolvedValue({
      batch: {
        id: 2,
        created_at: "2026-09-10T12:00:00Z",
        as_of_date: "2026-09-10",
        file_sha256: "barclays-hash",
        filename: "portfolio.xls",
        diff_summary: null,
      },
      summary: {},
    });
    const { container } = show();
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"][accept=".xls"]');
    expect(fileInput).not.toBeNull();
    fireEvent.change(fileInput!, { target: { files: [file] } });
    const dateInput = container.querySelector<HTMLInputElement>('input[type="date"]');
    expect(dateInput).not.toBeNull();
    fireEvent.change(dateInput!, { target: { value: "2026-09-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Import Barclays XLS snapshot" }));
    await waitFor(() => expect(importXls).toHaveBeenCalledWith(file, "2026-09-10", false));
    expect(await screen.findByText("Import complete.")).toBeInTheDocument();
    expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
    expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
  });

  it("keeps the Trading 212 refresh disabled when credentials are not configured", async () => {
    vi.mocked(api.getTrading212Status).mockResolvedValue({ configured: false, account_name: "Trading 212" });
    show();
    expect(await screen.findByRole("button", { name: "Sync Trading 212" })).toBeDisabled();
    expect(await screen.findByText(/credentials to .env/)).toBeInTheDocument();
  });

});
