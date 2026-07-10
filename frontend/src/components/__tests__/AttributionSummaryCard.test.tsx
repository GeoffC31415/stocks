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
    expect(screen.getByText(/£1,000.*£1,300/)).toBeInTheDocument();
    expect(screen.getByText("Net external flows")).toBeInTheDocument();
    expect(screen.getByText("+£50")).toBeInTheDocument();
    expect(screen.getByText("DRIP proxy")).toBeInTheDocument();
    expect(screen.getByText("£20")).toBeInTheDocument();
    expect(screen.getByText("Estimated market movement")).toBeInTheDocument();
    expect(screen.getByText("+£230")).toBeInTheDocument();
    expect(screen.getByText("Alpha fund")).toBeInTheDocument();
    expect(screen.getByText("Beta fund")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /full snapshot changes/i })).toHaveAttribute(
      "href",
      "/diff?from=4&to=5",
    );
  });

  it("shows an explicit unavailable state instead of zeroes", () => {
    render(
      <AttributionSummaryCard
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
          notes: ["No previous snapshot is available for this selection."],
        }}
      />,
    );

    expect(screen.getByText("Attribution unavailable")).toBeInTheDocument();
    expect(screen.getByText(/No previous snapshot/)).toBeInTheDocument();
  });
});
