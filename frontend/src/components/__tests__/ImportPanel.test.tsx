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

  it("syncs a portfolio snapshot without a file upload", async () => {
    show();

    const button = await screen.findByRole("button", {
      name: "Sync Trading 212 snapshot",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(api.syncTrading212Portfolio).toHaveBeenCalledOnce());
    expect(await screen.findByText("Trading 212 snapshot synced.")).toBeInTheDocument();
  });

  it("syncs order history without applying the DRIP threshold", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Order history" }));

    const button = await screen.findByRole("button", {
      name: "Sync Trading 212 orders",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(api.syncTrading212Orders).toHaveBeenCalledOnce());
    expect(await screen.findByText("Imported 1 Trading 212 orders.")).toBeInTheDocument();
  });
});
