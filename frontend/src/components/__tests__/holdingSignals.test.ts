import { describe, expect, it } from "vitest";
import { holdingPerformanceSignals } from "../holdingSignals";

describe("holdingPerformanceSignals", () => {
  it("describes evidence without issuing buy or sell instructions", () => {
    const labels = holdingPerformanceSignals({
      latestPctChange: 42.5,
      drawdownFromPeakPct: -2.1,
      quantityUnchangedSnapshotCount: 4,
    }).map((signal) => signal.label);

    expect(labels).toContain("42.50% gain · 2.1% below peak");
    expect(labels.join(" ").toLowerCase()).not.toMatch(/trim|top.?up|buy|sell/);
  });

  it("describes a sustained loss neutrally", () => {
    expect(
      holdingPerformanceSignals({
        latestPctChange: -15,
        drawdownFromPeakPct: -18,
        quantityUnchangedSnapshotCount: 3,
      }),
    ).toContainEqual({ label: "-15.00% P&L · quantity unchanged for 3 snapshots", tone: "rose" });
  });
});
