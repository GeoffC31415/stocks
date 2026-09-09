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

});
