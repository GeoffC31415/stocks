import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { Topbar } from "../Topbar";

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ session: { mode: "passkey" }, logout: vi.fn() }),
}));

const summary = {
  as_of_date: "2026-07-05",
  import_batch_id: 22,
  total_value_gbp: 100,
  total_book_cost_gbp: 80,
  total_pnl_gbp: 20,
  by_account: { ISA: 60, Trading: 40 },
  by_group: {},
  allocation: [],
  group_allocation: [],
  worst_pct: [],
  best_pct: [],
};

function LocationProbe() {
  return <output data-testid="route">{useLocation().pathname}</output>;
}

describe("Topbar", () => {
  beforeEach(() => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
    vi.spyOn(api,"getSyncStatus").mockResolvedValue({manual_sync_enabled:false,accounts:[],stale_after_days:7,running:false,last_run:null,outcome:"partial"});
  });

  it("provides a compact account selector for narrow screens", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PreferencesContext.Provider
            value={{
              dripThreshold: 1000,
              setDripThreshold: vi.fn(),
              accountFilter: "all",
              setAccountFilter: vi.fn(),
            }}
          >
            <Topbar />
            <LocationProbe />
          </PreferencesContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const selector = await screen.findByRole("combobox", { name: "Account" });
    expect(selector).toHaveValue("all");
    expect(screen.getByRole("button", { name: /refresh data/i })).toBeInTheDocument();
    expect(await screen.findByText("Refresh outcome: partial")).not.toHaveClass("text-pos");
    expect(screen.getByRole("combobox", { name: "Performance period" })).toHaveValue("ALL");
    expect(screen.getByRole("button", { name: "Analysis settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Passkey security" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Passkey security" }));
    expect(screen.getByTestId("route")).toHaveTextContent("/security");
    expect(screen.queryByText("DRIP threshold")).not.toBeInTheDocument();
    expect(screen.queryByText("£1,000")).not.toBeInTheDocument();
  });
});
