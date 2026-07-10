export type HoldingSignal = {
  label: string;
  tone: "amber" | "rose";
};

const LOSS_THRESHOLD_PCT = -10;
const UNCHANGED_SNAPSHOT_COUNT = 3;
const GAIN_THRESHOLD_PCT = 20;
const NEAR_PEAK_DRAWDOWN_PCT = -5;

export function holdingPerformanceSignals({
  latestPctChange,
  drawdownFromPeakPct,
  quantityUnchangedSnapshotCount,
}: {
  latestPctChange: number | null;
  drawdownFromPeakPct: number | null;
  quantityUnchangedSnapshotCount: number | null;
}): HoldingSignal[] {
  const signals: HoldingSignal[] = [];

  if (
    latestPctChange != null &&
    drawdownFromPeakPct != null &&
    latestPctChange >= GAIN_THRESHOLD_PCT &&
    drawdownFromPeakPct >= NEAR_PEAK_DRAWDOWN_PCT
  ) {
    signals.push({
      label: `${latestPctChange.toFixed(2)}% gain · ${Math.abs(drawdownFromPeakPct).toFixed(1)}% below peak`,
      tone: "amber",
    });
  }

  if (
    latestPctChange != null &&
    quantityUnchangedSnapshotCount != null &&
    latestPctChange <= LOSS_THRESHOLD_PCT &&
    quantityUnchangedSnapshotCount >= UNCHANGED_SNAPSHOT_COUNT
  ) {
    signals.push({
      label: `${latestPctChange.toFixed(2)}% P&L · quantity unchanged for ${quantityUnchangedSnapshotCount} snapshots`,
      tone: "rose",
    });
  }

  return signals;
}
