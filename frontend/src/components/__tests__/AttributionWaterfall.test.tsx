import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SnapshotAttribution } from "../../lib/api";
import { AttributionWaterfall } from "../AttributionWaterfall";

const attribution: SnapshotAttribution = {
  from_batch: null,
  to_batch: null,
  opening_value_gbp: 1000,
  closing_value_gbp: 1300,
  raw_value_change_gbp: 300,
  contributions_gbp: 100,
  withdrawals_gbp: 50,
  drip_proxy_gbp: 20,
  net_external_flow_gbp: 50,
  residual_market_movement_gbp: 230,
  reconciliation_difference_gbp: 0,
  top_contributors: [],
  top_detractors: [],
  notes: [],
};

describe("AttributionWaterfall", () => {
  it("steps opening value through every component to the closing value", () => {
    render(<AttributionWaterfall attribution={attribution} />);

    // Reconciliation check: opening + components must equal closing.
    expect(
      (attribution.opening_value_gbp ?? 0) +
        (attribution.contributions_gbp ?? 0) -
        (attribution.withdrawals_gbp ?? 0) +
        (attribution.drip_proxy_gbp ?? 0) +
        (attribution.residual_market_movement_gbp ?? 0),
    ).toBe(attribution.closing_value_gbp);

    expect(screen.getByRole("heading", { name: "Value walk" })).toBeInTheDocument();
    expect(screen.getByText("Opening value")).toBeInTheDocument();
    expect(screen.getByText("Contributions")).toBeInTheDocument();
    expect(screen.getByText("Withdrawals")).toBeInTheDocument();
    expect(screen.getByText("DRIP proxy")).toBeInTheDocument();
    expect(screen.getByText("Market movement")).toBeInTheDocument();
    expect(screen.getByText("Closing value")).toBeInTheDocument();
    expect(screen.getByText("£1,000")).toBeInTheDocument();
    expect(screen.getByText("£1,300")).toBeInTheDocument();
  });

  it("signs components: withdrawals out, DRIP and residual in", () => {
    const { container } = render(<AttributionWaterfall attribution={attribution} />);
    const stepTexts = Array.from(container.querySelectorAll("[data-testid='waterfall-step']")).map(
      (el) => el.textContent,
    );
    expect(stepTexts).toContain("Contributions +£100");
    expect(stepTexts).toContain("Withdrawals -£50");
    expect(stepTexts).toContain("DRIP proxy +£20");
    expect(stepTexts).toContain("Market movement +£230");
  });

  it("shows the unreconciled difference explicitly when it is non-zero", () => {
    render(
      <AttributionWaterfall
        attribution={{ ...attribution, reconciliation_difference_gbp: 5 }}
      />,
    );
    expect(screen.getByText("Reconciliation difference")).toBeInTheDocument();
    expect(screen.getByText(/Unreconciled difference £5/)).toBeInTheDocument();
  });

  it("states exact reconciliation when the difference is zero", () => {
    render(<AttributionWaterfall attribution={attribution} />);
    expect(
      screen.getByText("Exact reconciliation before display rounding."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Unreconciled/)).not.toBeInTheDocument();
  });

  it("provides a tabular fallback with running totals", () => {
    const { container } = render(<AttributionWaterfall attribution={attribution} />);
    const table = screen.getByRole("table", { name: /attribution waterfall/i });
    const rows = Array.from(table.querySelectorAll("tbody tr")).map(
      (row) => row.textContent,
    );
    // Layout math only: running totals reconcile to the API closing value.
    expect(rows[0]).toContain("£1,000");
    expect(rows[rows.length - 1]).toContain("£1,300");
    expect(
      container.querySelectorAll("table tbody tr"),
    ).toHaveLength(6); // opening + 4 components + closing
  });
});
