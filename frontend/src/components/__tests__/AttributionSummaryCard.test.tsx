import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SnapshotAttribution } from "../../lib/api";
import { AttributionSummaryCard } from "../AttributionSummaryCard";

const attribution: SnapshotAttribution = {
  from_batch: {
    id: 4,
    created_at: "2025-01-01T10:00:00Z",
    as_of_date: "2025-01-01",
    file_sha256: "from",
    filename: "from.csv",
    diff_summary: null,
  },
  to_batch: {
    id: 5,
    created_at: "2025-02-01T10:00:00Z",
    as_of_date: "2025-02-01",
    file_sha256: "to",
    filename: "to.csv",
    diff_summary: null,
  },
  opening_value_gbp: 1000,
  closing_value_gbp: 1300,
  raw_value_change_gbp: 300,
  contributions_gbp: 100,
  withdrawals_gbp: 50,
  drip_proxy_gbp: 20,
  net_external_flow_gbp: 50,
  residual_market_movement_gbp: 230,
  reconciliation_difference_gbp: 0,
  top_contributors: [
    {
      instrument_id: 1,
      identifier: "AAA",
      security_name: "Alpha fund",
      account_name: "ISA",
      opening_value_gbp: 600,
      closing_value_gbp: 850,
      raw_value_change_gbp: 250,
      net_external_flow_gbp: 100,
      drip_proxy_gbp: 20,
      estimated_market_movement_gbp: 130,
    },
  ],
  top_detractors: [
    {
      instrument_id: 2,
      identifier: "BBB",
      security_name: "Beta fund",
      account_name: "ISA",
      opening_value_gbp: 500,
      closing_value_gbp: 450,
      raw_value_change_gbp: -50,
      net_external_flow_gbp: 0,
      drip_proxy_gbp: 0,
      estimated_market_movement_gbp: -50,
    },
  ],
  notes: ["Residual market movement is an attribution estimate."],
};

describe("AttributionSummaryCard", () => {
  it("summarises boundaries, flows, DRIP, market movement and movers", () => {
    render(<AttributionSummaryCard attribution={attribution} />);

    expect(screen.getByText("What changed")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Opening value £1,000" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "Closing value £1,300" })).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getByRole("table")).toBeVisible();
    expect(screen.getByText("DRIP proxy")).toBeInTheDocument();
    expect(screen.getByText("+£20")).toBeInTheDocument();
    expect(screen.getByText("Estimated market movement")).toBeInTheDocument();
    expect(screen.getByText("+£230")).toBeInTheDocument();
    expect(screen.getByText("Alpha fund")).toBeInTheDocument();
    expect(screen.getByText("Beta fund")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /full snapshot changes/i })).toHaveAttribute(
      "href",
      "/activity?tab=changes&from=4&to=5",
    );
    expect(screen.queryByText("Value walk")).not.toBeInTheDocument();
    expect(screen.getByText("Residual market movement is an attribution estimate.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Alpha fund/ })).toHaveAttribute("href", "/activity?tab=changes&from=4&to=5&account=ISA&inst=1");
    expect(
      screen.getByText("Exact reconciliation before display rounding."),
    ).toBeInTheDocument();
  });

  it("surfaces a non-zero reconciliation difference in the waterfall", () => {
    render(
      <AttributionSummaryCard
        attribution={{ ...attribution, reconciliation_difference_gbp: 5 }}
      />,
    );
    expect(screen.getByText("Reconciliation difference")).toBeInTheDocument();
    expect(screen.getByText(/Unreconciled difference £5/)).toBeInTheDocument();
  });

  it("keeps the dashboard breakdown, movers and material warnings without routine prose", () => {
    render(<AttributionSummaryCard compact attribution={{ ...attribution, unallocated_residual_gbp: 15, notes: [
      ...attribution.notes,
      "2 flow order(s) were not linked to an instrument; per-instrument estimates do not allocate those flows.",
      "Some account valuations are carried forward at these boundaries; market movement is not synchronously observed.",
    ] }} />);
    expect(screen.getByRole("row", { name: "Closing value £1,300" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Alpha fund/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /full snapshot changes/i })).toBeVisible();
    expect(screen.getByText("Unallocated residual adjustment: +£15.")).toBeVisible();
    expect(screen.getByText("Some account values were carried forward.")).toBeVisible();
    expect(screen.getByText("2 unlinked orders are not allocated to holdings.")).toBeVisible();
    expect(screen.queryByText("Residual market movement is an attribution estimate.")).not.toBeInTheDocument();
    expect(screen.queryByText("Exact reconciliation before display rounding.")).not.toBeInTheDocument();
  });

  it.each([false, true])("shows the actual reason when attribution is unavailable (compact=%s)", (compact) => {
    render(
      <AttributionSummaryCard
        compact={compact}
        attribution={{
          ...attribution,
          from_batch: null,
          opening_value_gbp: null,
          closing_value_gbp: null,
          raw_value_change_gbp: null,
          contributions_gbp: null,
          withdrawals_gbp: null,
          drip_proxy_gbp: null,
          net_external_flow_gbp: null,
          residual_market_movement_gbp: null,
          reconciliation_difference_gbp: null,
          top_contributors: [],
          top_detractors: [],
          notes: [...attribution.notes, "No previous snapshot is available for this selection."],
        }}
      />,
    );

    expect(screen.getByText("Attribution unavailable")).toBeInTheDocument();
    expect(screen.getByText(/No previous snapshot/)).toBeVisible();
    if (compact) expect(screen.queryByText(attribution.notes[0])).not.toBeInTheDocument();
  });
});
