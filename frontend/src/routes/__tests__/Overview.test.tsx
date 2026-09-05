import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type PortfolioSummary } from "../../lib/api";
import { Overview } from "../Overview";
import { PreferencesContext } from "../../state/usePreferences";

vi.mock("../../components/HeroKpi", () => ({ HeroKpi: ({ value }: { value: number }) => <div>Portfolio balance: {value}</div> }));
vi.mock("../../components/PerformancePanel", () => ({ PerformancePanel: () => <div>Performance workspace</div> }));
vi.mock("../../components/ChartPanel", () => ({ ChartPanel: () => null }));
vi.mock("../../components/DataConfidencePanel", () => ({ DataConfidencePanel: () => null }));
vi.mock("../../components/PerformersSection", () => ({ PerformersSection: () => null }));
vi.mock("../../components/AttributionSummaryCard", () => ({ AttributionSummaryCard: () => null }));

const zero: PortfolioSummary = {
  as_of_date: "2026-01-01", import_batch_id: 1, total_value_gbp: 0,
  total_book_cost_gbp: 0, total_pnl_gbp: 0, by_account: { ISA: 0 }, by_group: {},
  allocation: [], group_allocation: [], worst_pct: [], best_pct: [],
};

function show(account = "all") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>
    <PreferencesContext.Provider value={{ accountFilter: account, dripThreshold: 100,
      setAccountFilter: () => {}, setDripThreshold: () => {} }}><Overview /></PreferencesContext.Provider>
  </MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.spyOn(api, "getInstruments").mockResolvedValue([]);
  vi.spyOn(api, "getPerformance").mockRejectedValue(new Error("performance offline"));
  vi.spyOn(api, "getTimeseries").mockResolvedValue([]);
  vi.spyOn(api, "getCashflowTimeseries").mockResolvedValue([]);
  vi.spyOn(api, "getOrderAnalytics").mockRejectedValue(new Error("orders offline"));
  vi.spyOn(api, "getSnapshotAttribution").mockRejectedValue(new Error("attribution offline"));
  vi.spyOn(api, "getPortfolioReturns").mockRejectedValue(new Error("returns offline"));
});

describe("Overview states", () => {
  it("keeps the dashboard compact and links to the relocated full analysis", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(zero);
    show();
    await screen.findByText("Portfolio balance: 0");
    expect(api.getOrderAnalytics).not.toHaveBeenCalled();
    expect(api.getCashflowTimeseries).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Full performance analysis" })).toHaveAttribute("href", "/portfolio?tab=performance");
    expect(screen.queryByText("Performance leaders")).not.toBeInTheDocument();
  });
  it("uses the selected account API totals even when instrument details are empty", async () => {
    const summary = vi.spyOn(api, "getSummary").mockResolvedValue({ ...zero, position_count: 15, total_value_gbp: 12345 });
    show("ISA");
    expect(await screen.findByText("Portfolio balance: 12345")).toBeInTheDocument();
    expect(summary).toHaveBeenCalledWith("ISA");
    expect(api.getInstruments).not.toHaveBeenCalled();
  });
  it("discloses an empty selected account rather than a zero all-account balance", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue({ ...zero, position_count: 0, total_value_gbp: 0 });
    show("Empty account");
    expect(await screen.findByText("No holdings for the selected account.")).toBeInTheDocument();
    expect(screen.queryByText("Portfolio balance: 0")).not.toBeInTheDocument();
  });

  it("keeps loading distinct from empty and error", () => {
    vi.spyOn(api, "getSummary").mockImplementation(() => new Promise(() => {}));
    show();
    expect(screen.getByText("Loading portfolio…")).toBeInTheDocument();
    expect(screen.queryByText("Welcome to your portfolio")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not welcome users to import when summary fetching failed", async () => {
    vi.spyOn(api, "getSummary").mockRejectedValue(new Error("offline"));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load portfolio summary");
    expect(screen.queryByText("Welcome to your portfolio")).not.toBeInTheDocument();
    vi.mocked(api.getSummary).mockResolvedValue(zero);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Portfolio balance: 0")).toBeInTheDocument();
  });
  it("treats a dated zero balance as valid, not an empty portfolio", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(zero);
    show();
    expect(await screen.findByText("Portfolio balance: 0")).toBeInTheDocument();
    expect(screen.queryByText("Welcome to your portfolio")).not.toBeInTheDocument();
    expect(api.getPortfolioReturns).not.toHaveBeenCalled();
  });
  it("offers import only for a successful empty summary", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue({ ...zero, as_of_date: null, import_batch_id: null });
    show();
    expect(await screen.findByText("Welcome to your portfolio")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import data" })).toBeInTheDocument();
  });
});
