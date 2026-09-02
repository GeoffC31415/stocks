import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api, type PerformanceSummary } from "../../lib/api";
import { PerformancePanel } from "../PerformancePanel";

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
    // On error, useQuery.data is undefined -> the panel falls back to the
    // "not enough snapshot history" branch.
    await waitFor(() =>
      expect(screen.getByText(/Not enough snapshot history yet/)).toBeInTheDocument(),
    );
  });
});
