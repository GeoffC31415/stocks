import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { ImportActivity } from "../ImportActivity";

const imports = [
  {
    id: 22,
    created_at: "2026-07-05T12:00:00Z",
    as_of_date: "2026-07-05",
    filename: "portfolio.xls",
    file_sha256: "hash",
    diff_summary: null,
  },
];

describe("ImportActivity", () => {
  beforeEach(() => {
    vi.spyOn(api, "getImports").mockResolvedValue(imports);
    vi.spyOn(api, "getUnlinkedOrders").mockResolvedValue({ count: 0, orders: [] });
  });

  it("shows immutable import history without upload controls", async () => {
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
            <ImportActivity />
          </PreferencesContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("portfolio.xls")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Import history" })).toBeInTheDocument();
    expect(screen.queryByText("Choose .xls file")).not.toBeInTheDocument();
  });
});
