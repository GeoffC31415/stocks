import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api, type PerformanceSummary } from "../../lib/api";
import { PerformancePanel } from "../PerformancePanel";
import { AnalysisScopeContext } from "../../state/useAnalysisScope";

// Recharts renders SVG in jsdom (no layout); assert on the text we control.

const basePerf: PerformanceSummary = {
  period: "ALL",
  coverage_start: null,
  period_start: "2026-01-01",
  period_end: "2026-02-01",
  start_value_gbp: 100,
  end_value_gbp: 200,
  total_return_pct: 100.0,
  annualised_return_pct: null,
  annualised_volatility_pct: null,
  sharpe_ratio: null,
  sortino_ratio: null,
  max_drawdown_pct: 0.0,
  max_drawdown_raw_pct: 0.0,
  best_period_return_pct: 100.0,
  worst_period_return_pct: 100.0,
  num_periods: 1,
  annualisation_factor: null,
  risk_free_annual_pct: 0,
  method: "arithmetic",
  notes: [],
  growth_curve: [
    { as_of_date: "2026-01-01", value_gbp: 100, normalized_value: 100 },
    { as_of_date: "2026-02-01", value_gbp: 200, normalized_value: 200 },
  ],
  benchmarks: [],
  flow_adjusted_curve: [
    { date: "2026-01-01", index: 100 },
    { date: "2026-02-01", index: 100 },
  ],
  drawdown_curve: [
    { date: "2026-01-01", index: 100, drawdown_pct: 0, at_peak: true },
    { date: "2026-02-01", index: 100, drawdown_pct: 0, at_peak: true },
  ],
  flow_adjusted: {
    contributions_gbp: 100,
    withdrawals_gbp: 0,
    net_external_flow_gbp: 100,
    total_return_pct: 0.0,
    annualised_return_pct: null,
    annualised_volatility_pct: null,
    sharpe_ratio: null,
    sortino_ratio: null,
    num_periods: 1,
    annualisation_factor: null,
    method: "Modified Dietz",
    notes: ["flow-adjusted"],
    flow_adjusted_curve: [
      { date: "2026-01-01", index: 100 },
      { date: "2026-02-01", index: 100 },
    ],
    drawdown_curve: [
      { date: "2026-01-01", index: 100, drawdown_pct: 0, at_peak: true },
      { date: "2026-02-01", index: 100, drawdown_pct: 0, at_peak: true },
    ],
    max_drawdown_pct: 0.0,
  },
};

function renderPanel(ui: React.ReactNode, perfOverride?: PerformanceSummary) {
  const getPerformance = vi.fn(async () => perfOverride ?? basePerf);
  vi.spyOn(api, "getPerformance").mockImplementation(getPerformance);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const utils = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  return { ...utils, getPerformance };
}

describe("PerformancePanel", () => {
  it("keys requests by shared period and account and hides old metrics while the next scope loads", async () => {
    const request = vi.spyOn(api, "getPerformance").mockResolvedValue(basePerf);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const panel = (account: string, period: "ALL" | "1M") => <QueryClientProvider client={client}>
      <AnalysisScopeContext.Provider value={{ period, setPeriod: vi.fn() }}>
        <PerformancePanel accountName={account} />
      </AnalysisScopeContext.Provider>
    </QueryClientProvider>;
    const view = render(panel("ISA", "ALL"));
    await screen.findByText("Performance");
    expect(request).toHaveBeenLastCalledWith("ISA", "ALL");
    request.mockImplementation(() => new Promise(() => {}));
    view.rerender(panel("Trading", "1M"));
    await screen.findByText("Crunching performance…");
    expect(request).toHaveBeenLastCalledWith("Trading", "1M");
    expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
  });
  it("honours unavailable metadata even when legacy payload contains curves and numbers", async () => {
    renderPanel(<PerformancePanel />, {
      ...basePerf,
      metrics: { total_return_pct: {
        status: "unavailable", value: null, unit: "percent", method: "Chain-linked Dietz",
        start_date: "2026-01-01", end_date: "2026-02-01", observations: 2,
        reasons: [{ code: "invalid_return_chain", message: "A correction left an unusable interval.", action_href: null }],
      } },
    });
    await screen.findByText("Performance");
    expect(screen.getAllByText("A correction left an unusable interval.").length).toBeGreaterThan(0);
    expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
    expect(screen.queryByText("Flow-adjusted drawdown")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("explains missing annualisation separately without hiding a valid cumulative chart", async () => {
    renderPanel(<PerformancePanel />, {
      ...basePerf,
      metrics: { annualised_return_pct: {
        status: "unavailable", value: null, unit: "percent", method: "Dietz",
        start_date: "2026-01-01", end_date: "2026-02-01", observations: 2,
        reasons: [{ code: "short_window", message: "Annualisation needs 365 days.", action_href: null }],
      } },
    });
    expect(await screen.findByText("Annualisation needs 365 days.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Snapshot performance chart" })).toBeInTheDocument();
    expect(screen.queryByText(/Typical:/)).not.toBeInTheDocument();
  });

  it("never substitutes raw metrics when flow-adjusted metrics are unavailable", async () => {
    renderPanel(<PerformancePanel />, { ...basePerf, annualised_return_pct: 123, annualised_volatility_pct: 45, sharpe_ratio: 6, sortino_ratio: 7, flow_adjusted_curve: [], drawdown_curve: [], flow_adjusted: { ...basePerf.flow_adjusted!, total_return_pct: null, annualised_return_pct: null, annualised_volatility_pct: null, sharpe_ratio: null, sortino_ratio: null, flow_adjusted_curve: [], drawdown_curve: [] } });
    await screen.findByText("Performance");
    for (const label of ["Snapshot investment return", "Annualised", "Volatility", "Sharpe", "Sortino", "Max drawdown"]) {
      const tile = screen.getByText(label).parentElement!.parentElement!;
      expect(tile.querySelector("p.tabular")).toHaveTextContent("—");
    }
    expect(screen.getByText(/Flow-adjusted performance unavailable/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "About Snapshot investment return" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Chain-linked interval Modified Dietz");
    expect(screen.getByText("raw 100.00%")).toBeInTheDocument();
  });
  it("shows a loading state while the query is pending", async () => {
    let resolve!: (value: PerformanceSummary) => void;
    const getPerformance = vi.fn(
      () =>
        new Promise<PerformanceSummary>((r) => {
          resolve = r;
        }),
    );
    vi.spyOn(api, "getPerformance").mockImplementation(getPerformance);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <PerformancePanel />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Crunching performance/)).toBeInTheDocument();
    resolve(basePerf);
    await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
  });

  it("shows an explicit unavailable state when there is no curve", async () => {
    const empty: PerformanceSummary = {
      ...basePerf,
      growth_curve: [],
      flow_adjusted_curve: [],
      drawdown_curve: [],
      flow_adjusted: undefined,
    };
    renderPanel(<PerformancePanel />, empty);
    await waitFor(() =>
      expect(screen.getByText(/Not enough snapshot history yet/)).toBeInTheDocument(),
    );
  });

  it("cash-flow regression: pure contribution keeps the flow-adjusted drawdown at 0", async () => {
    // Raw value doubles (100 -> 200) from a single contribution with no market
    // gain; the flow-adjusted index is flat, so the KPI max drawdown is 0 and
    // the subline shows the raw drawdown distinctly.
    renderPanel(<PerformancePanel />);
    await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
    // The KPI tile's subline distinguishes the flow-adjusted value from the raw one.
    expect(screen.getByText("flow-adjusted · raw 0.00%")).toBeInTheDocument();
  });

  it("keeps the raw value overlay hidden by default and reveals it on toggle", async () => {
    const { container } = renderPanel(<PerformancePanel />);
    await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());

    // Default: raw value is not drawn and only the flow-adjusted legend is present.
    expect(screen.queryByText("Raw account value (index, optional)")).not.toBeInTheDocument();
    expect(screen.getByText(/Flow-adjusted \(index, 100 = window start\)/)).toBeInTheDocument();

    const toggle = screen.getByLabelText(/Show raw account value/i);
    fireEvent.click(toggle);
    expect(screen.getByText("Raw account value (index, optional)")).toBeInTheDocument();
    expect(container).toBeTruthy();
  });

  it("shows an error state without crashing", async () => {
    vi.spyOn(api, "getPerformance").mockRejectedValue(new Error("boom"));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <PerformancePanel />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load performance");
    expect(screen.queryByText(/Not enough snapshot history yet/)).not.toBeInTheDocument();
    vi.mocked(api.getPerformance).mockResolvedValue(basePerf);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Performance")).toBeInTheDocument();
  });
});
