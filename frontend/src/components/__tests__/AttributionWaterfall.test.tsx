import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SnapshotAttribution } from "../../lib/api";
import { AttributionWaterfall } from "../AttributionWaterfall";

const attribution: SnapshotAttribution = {
  from_batch: null, to_batch: null, opening_value_gbp: 1000, closing_value_gbp: 1300,
  raw_value_change_gbp: 300, contributions_gbp: 100, withdrawals_gbp: 50, drip_proxy_gbp: 20,
  net_external_flow_gbp: 50, residual_market_movement_gbp: 230, reconciliation_difference_gbp: 0,
  top_contributors: [], top_detractors: [], notes: [],
};

describe("compact attribution breakdown", () => {
  it("renders exactly one six-row table and no value-walk SVG or duplicated screen-reader table", () => {
    const { container } = render(<AttributionWaterfall attribution={attribution} />);
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getAllByRole("row")).toHaveLength(6);
    expect(screen.queryByText("Value walk")).not.toBeInTheDocument();
  });
  it("keeps the authoritative opening and closing values", () => {
    render(<AttributionWaterfall attribution={attribution} />);
    expect(screen.getByRole("row", { name: "Opening value £1,000" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Closing value £1,300" })).toBeInTheDocument();
  });
  it("signs movements without implying the residual is a proven price effect", () => {
    render(<AttributionWaterfall attribution={attribution} />);
    expect(screen.getByRole("row", { name: "Contributions +£100" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Withdrawals −£50" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "DRIP proxy +£20" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Estimated market movement +£230" })).toBeInTheDocument();
  });
  it("reports a reconciliation difference", () => {
    render(<AttributionWaterfall attribution={{ ...attribution, reconciliation_difference_gbp: 5 }} />);
    expect(screen.getByText(/Unreconciled difference £5/)).toBeInTheDocument();
  });
  it("reports exact reconciliation only when the backend supplies it", () => {
    render(<AttributionWaterfall attribution={attribution} />);
    expect(screen.getByText("Exact reconciliation before display rounding.")).toBeInTheDocument();
  });
  it("does not turn missing components or reconciliation into zero", () => {
    render(<AttributionWaterfall attribution={{ ...attribution, contributions_gbp: null, reconciliation_difference_gbp: null }} />);
    expect(screen.getByRole("row", { name: "Contributions Unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Reconciliation unavailable.")).toBeInTheDocument();
  });
});
