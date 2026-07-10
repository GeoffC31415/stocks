import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PortfolioReturnSummary } from "../../lib/api";
import { PortfolioReturnCard } from "../PortfolioReturnCard";

const summary: PortfolioReturnSummary = {
  period_start: "2025-01-01",
  period_end: "2025-12-31",
  start_value_gbp: 1000,
  end_value_gbp: 1200,
  contributions_gbp: 100,
  withdrawals_gbp: 0,
  net_external_flow_gbp: 100,
  absolute_gain_after_flows_gbp: 100,
  modified_dietz_return_pct: 9.52,
  annualised_return_pct: null,
  method: "Modified Dietz",
  notes: [],
};

describe("PortfolioReturnCard", () => {
  it("shows the Modified Dietz return with method and period context", () => {
    render(<PortfolioReturnCard summary={summary} />);

    expect(screen.getByText("Money-weighted return")).toBeInTheDocument();
    expect(screen.getByText("+9.52%")).toBeInTheDocument();
    expect(screen.getByText(/Modified Dietz/)).toBeInTheDocument();
    expect(screen.getByText(/1 Jan 2025.*31 Dec 2025/)).toBeInTheDocument();
  });

  it("shows a clear unavailable state instead of inventing a return", () => {
    render(
      <PortfolioReturnCard
        summary={{
          ...summary,
          period_start: null,
          period_end: null,
          modified_dietz_return_pct: null,
          notes: ["At least two snapshot dates are required to calculate a return."],
        }}
      />,
    );

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText(/At least two snapshot dates/)).toBeInTheDocument();
  });
});
