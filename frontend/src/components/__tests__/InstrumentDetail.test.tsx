import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { InstrumentDetail } from "../InstrumentDetail";
import type { Instrument, InstrumentHistoryPoint, Order } from "../../lib/api";

const history: InstrumentHistoryPoint[] = [
  { as_of_date: "2026-01-01", value_gbp: 100, book_cost_gbp: 100, discretionary_cost_basis_gbp: 100, quantity: 1, pct_change: 0 },
  { as_of_date: "2026-02-01", value_gbp: 110, book_cost_gbp: 100, discretionary_cost_basis_gbp: 100, quantity: 1, pct_change: 10 },
];
const instrument = { id: 1, account_name: "ISA", identifier: "TEST-1", ticker: "TEST", asset_class: "Equity", sector: "Technology" } as Instrument;
const order = (id: number, side: string, is_drip: boolean, order_date: string): Order => ({
  id, side, is_drip, order_date, security_name: "Test fund", instrument_id: 1, instrument: null,
  order_status: "Executed", account_name: "ISA", quantity: 1, cost_proceeds_gbp: 10,
  country: null, match_status: "matched", match_method: "test", match_confidence: 1, matched_at: null,
});

function renderDetail(orders: Order[]) {
  return render(<MemoryRouter initialEntries={["/portfolio?tab=holdings&inst=1"]}>
    <InstrumentDetail name="Test fund" instrument={instrument} trailingDripYieldPct={null}
      history={history} historyLoading={false} orders={orders} ordersLoading={false} hasOrders />
  </MemoryRouter>);
}

describe("InstrumentDetail buy markers", () => {
  it("identifies dashed buy-date markers and labels that DRIP is excluded", () => {
    renderDetail([order(1, "Buy", false, "2026-01-15")]);
    expect(screen.getByText("Buy dates (DRIP excluded)")).toBeInTheDocument();
  });

  it("shows a separate sell-date marker when the instrument has a sell", () => {
    renderDetail([order(4, "Sell", false, "2026-03-01")]);
    expect(screen.getByText("Sell dates")).toBeInTheDocument();
    expect(screen.queryByText("Buy dates (DRIP excluded)")).not.toBeInTheDocument();
  });

  it("does not show buy markers for DRIP purchases or sells", () => {
    renderDetail([order(2, "Buy", true, "2026-01-20"), order(3, "Sell", false, "2026-01-25")]);
    expect(screen.queryByText("Buy dates (DRIP excluded)")).not.toBeInTheDocument();
  });
});
