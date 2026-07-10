import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { Topbar } from "../Topbar";

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

describe("Topbar", () => {
  beforeEach(() => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
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
          </PreferencesContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const selector = await screen.findByRole("combobox", { name: "Account" });
    expect(selector).toHaveValue("all");
    expect(screen.getByRole("button", { name: /refresh data/i })).toBeInTheDocument();
  });
});
