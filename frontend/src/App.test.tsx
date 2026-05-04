import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./lib/api", async () => {
  const actual = await vi.importActual<typeof import("./lib/api")>("./lib/api");
  const summary = {
    as_of_date: "2026-05-04",
    import_batch_id: 1,
    total_value_gbp: 0,
    total_book_cost_gbp: 0,
    total_pnl_gbp: 0,
    by_account: {},
    by_group: {},
    allocation: [],
    group_allocation: [],
    worst_pct: [],
    best_pct: [],
  };

  return {
    ...actual,
    api: {
      getSummary: vi.fn().mockResolvedValue(summary),
      getImports: vi.fn().mockResolvedValue([]),
      getUnlinkedOrders: vi.fn().mockResolvedValue({ count: 0, orders: [] }),
      importXls: vi.fn(),
      importHlHoldingsCsv: vi.fn(),
      importOrderXls: vi.fn(),
      importHlOrdersCsv: vi.fn(),
    },
  };
});

describe("App", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/import");
    window.localStorage.clear();
  });

  it("mounts against mocked API responses", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText("Import data")).not.toHaveLength(0);
    expect(await screen.findByText("No imports yet")).toBeInTheDocument();
  });
});
