import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AllocationResponse } from "../../lib/api";
import { PreferencesContext } from "../../state/usePreferences";
import { AllocationAnalysisPanel } from "../AllocationAnalysisPanel";

vi.mock("../../lib/api", () => ({ api: { getAllocation: vi.fn(), getInstruments: vi.fn().mockResolvedValue([]) } }));
const payload: AllocationResponse = {
  dimension: "asset_class", account_name: null, cash_policy: "excluded_all_dimensions",
  denominator_description: "Current positive GBP values of open non-cash holdings only.",
  totalValue: 1000, top1Pct: 80, top5Pct: 100, hhi: 6800,
  categories: [{ label: "Equity", value: 800, weightPct: 80, count: 1 }, { label: "Unclassified", value: 200, weightPct: 20, count: 1 }],
  holdings: [{ id: 1, identifier: "AAA", label: "Alpha", value: 800, weightPct: 80 }],
  classification: { holding_count: 2, classified_count: 1, classified_count_pct: 50, total_value_gbp: 1000, classified_value_gbp: 800, classified_value_pct: 80 },
};
function setup(account = "all") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const ui = (accountFilter: string) => <QueryClientProvider client={client}><MemoryRouter><PreferencesContext.Provider value={{ accountFilter, setAccountFilter: vi.fn(), dripThreshold: 1, setDripThreshold: vi.fn() }}><AllocationAnalysisPanel /></PreferencesContext.Provider></MemoryRouter></QueryClientProvider>;
  const view = render(ui(account));
  return { ...view, changeAccount: (value: string) => view.rerender(ui(value)) };
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getAllocation).mockResolvedValue(payload); });
describe("AllocationAnalysisPanel", () => {
  it("shows loading without fabricated zero metrics", () => {
    vi.mocked(api.getAllocation).mockReturnValue(new Promise(() => {}));
    setup();
    expect(screen.getByRole("status")).toHaveTextContent("Loading allocation");
    expect(screen.queryByText("Invested value")).not.toBeInTheDocument();
  });
  it("reports failure and retries the allocation query", async () => {
    vi.mocked(api.getAllocation).mockRejectedValueOnce(new Error("offline"));
    setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load allocation");
    expect(screen.queryByText("Invested value")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("AAA")).toBeInTheDocument();
  });
  it("discloses an empty eligible universe without claiming low concentration", async () => {
    vi.mocked(api.getAllocation).mockResolvedValue({ ...payload, totalValue: 0, top1Pct: 0, top5Pct: 0, hhi: 0, categories: [], holdings: [], classification: { holding_count: 0, classified_count: 0, classified_count_pct: 0, total_value_gbp: 0, classified_value_gbp: 0, classified_value_pct: 0 } });
    setup();
    expect(await screen.findByText(/No eligible positions/)).toBeInTheDocument();
    expect(screen.getByText(payload.denominator_description)).toBeInTheDocument();
    expect(screen.queryByText(/Lower concentration/)).not.toBeInTheDocument();
  });
  it("queries each dimension and account independently using accessible wrapping controls", async () => {
    const view = setup("ISA");
    await screen.findByText("AAA");
    expect(api.getAllocation).toHaveBeenCalledWith("asset_class", "ISA");
    for (const [name, dimension] of [["Sector", "sector"], ["Region", "region"], ["Account", "account"], ["Source currency", "currency"]]) {
      fireEvent.click(screen.getByRole("button", { name }));
      await waitFor(() => expect(api.getAllocation).toHaveBeenCalledWith(dimension, "ISA"));
      await screen.findByText("AAA");
      expect(screen.getByRole("button", { name, pressed: true })).toBeInTheDocument();
    }
    expect(screen.getByRole("table", { name: "By source currency" })).toBeInTheDocument();
    expect(screen.getByText(/not underlying FX exposure/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Allocation dimension" })).toHaveClass("flex-wrap");
    view.changeAccount("SIPP");
    await waitFor(() => expect(api.getAllocation).toHaveBeenCalledWith("currency", "SIPP"));
    await screen.findByText("AAA");
    fireEvent.click(screen.getByRole("button", { name: "Account" }));
    expect(await screen.findByRole("table", { name: "By account" })).toBeInTheDocument();
  });
  it("renders authoritative backend allocation and classification count/value coverage", async () => {
    setup();
    await waitFor(() => expect(api.getAllocation).toHaveBeenCalledWith("asset_class", null));
    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(api.getInstruments).not.toHaveBeenCalled();
    expect(screen.getByText(payload.denominator_description)).toBeInTheDocument();
    expect(screen.getByText(/Cash excluded in all dimensions/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 holdings.*50.0%/)).toBeInTheDocument();
    expect(screen.getByText(/£800 of £1,000.*80.0%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Complete classifications" })).toHaveAttribute("href", "/data?tab=classifications");
    expect(screen.getAllByText("6800")).toHaveLength(1); // one HHI headline, not a duplicate donut metric
  });
});
