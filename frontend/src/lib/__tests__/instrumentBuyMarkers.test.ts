import { describe, expect, it } from "vitest";
import type { Order } from "../api";
import { instrumentBuyMarkerDates, instrumentSellMarkerDates } from "../instrumentBuyMarkers";

const order = (id: number, side: string, is_drip: boolean, order_date: string) => ({
  id, side, is_drip, order_date,
} as Order);

describe("instrumentBuyMarkerDates", () => {
  it("returns sorted unique UTC calendar dates for non-DRIP buys only", () => {
    const markers = instrumentBuyMarkerDates([
      order(1, "Buy", false, "2026-02-02T15:30:00"),
      order(2, "buy", false, "2026-01-10"),
      order(3, "BUY", false, "2026-01-10T09:00:00Z"),
      order(4, "Buy", true, "2026-01-15"),
      order(5, "Sell", false, "2026-01-20"),
      order(6, "Buy", false, "not-a-date"),
    ]);

    expect(markers).toEqual([Date.UTC(2026, 0, 10), Date.UTC(2026, 1, 2)]);
  });

  it("returns sorted unique calendar dates for sells without treating buys as sales", () => {
    const markers = instrumentSellMarkerDates([
      order(1, "Sell", false, "2026-03-10T15:30:00"),
      order(2, "sell", false, "2026-02-05"),
      order(3, "SELL", false, "2026-02-05T09:00:00Z"),
      order(4, "Buy", false, "2026-01-15"),
      order(5, "Sell", false, "not-a-date"),
    ]);

    expect(markers).toEqual([Date.UTC(2026, 1, 5), Date.UTC(2026, 2, 10)]);
  });
});
