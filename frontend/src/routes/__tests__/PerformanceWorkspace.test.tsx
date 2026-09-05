import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { api } from "../../lib/api";
import { PerformanceWorkspace } from "../PerformanceWorkspace";
import { PreferencesContext } from "../../state/usePreferences";

vi.mock("../../components/PerformancePanel", () => ({ PerformancePanel: () => <div>Full performance metrics</div> }));
vi.mock("../../components/PortfolioReturnCard", () => ({ PortfolioReturnCard: () => null }));

it("keeps all three history views reachable and never requests a reconstruction benchmark", async () => {
  vi.spyOn(api, "getPerformance").mockRejectedValue(new Error("missing snapshots"));
  vi.spyOn(api, "getPortfolioReturns").mockRejectedValue(new Error("missing returns"));
  vi.spyOn(api, "getTimeseries").mockResolvedValue([]);
  vi.spyOn(api, "getCashflowTimeseries").mockResolvedValue([]);
  vi.spyOn(api, "getEstimatedTimeseries").mockResolvedValue([]);
  vi.spyOn(api, "getBenchmarks").mockResolvedValue([]);
  vi.spyOn(api, "getOrderAnalytics").mockResolvedValue({ total_orders: 1, total_buy_gbp: 100,
    total_drip_gbp: 0, total_sell_gbp: 0, cash_deployed_gbp: 100, net_cash_invested_gbp: 100,
    drip_count: 0, buy_count: 1, sell_count: 0, drip_threshold_gbp: 50, annual_drip: [], first_order_date: "2026-01-01" });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>
    <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 50, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
      <PerformanceWorkspace />
    </PreferencesContext.Provider>
  </MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Current-price reconstruction" }));
  expect(screen.getByRole("heading", { name: "Past holdings valued at today's prices" })).toBeInTheDocument();
  expect(screen.getByText(/not historical performance/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Capital deployment" }));
  expect(screen.getByRole("heading", { name: "Capital deployment" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Snapshot history" }));
  expect(screen.getByRole("heading", { name: "Snapshot history" })).toBeInTheDocument();
  expect(api.getEstimatedTimeseries).toHaveBeenCalledWith("ISA");
  expect(api.getBenchmarks).not.toHaveBeenCalled();
});
