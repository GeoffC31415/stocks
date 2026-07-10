import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Instrument } from "../../lib/api";
import { ClassificationQueue } from "../ClassificationQueue";

const incompleteInstrument = {
  id: 7,
  account_name: "ISA",
  identifier: "EQQQ",
  security_name: "NASDAQ ETF",
  is_cash: false,
  ticker: null,
  sector: null,
  region: null,
  asset_class: null,
  closed_at: null,
} as Instrument;

function renderQueue() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ClassificationQueue />
    </QueryClientProvider>,
  );
}

describe("ClassificationQueue", () => {
  beforeEach(() => {
    vi.spyOn(api, "getInstruments").mockResolvedValue([incompleteInstrument]);
    vi.spyOn(api, "updateInstrumentMarket").mockResolvedValue({
      ...incompleteInstrument,
      ticker: "EQQQ.L",
      asset_class: "Equity ETF",
    });
  });

  it("surfaces incomplete open instruments and saves reviewed metadata", async () => {
    renderQueue();

    expect(screen.getByRole("heading", { name: "Classification queue" })).toBeInTheDocument();
    const tickerInput = await screen.findByLabelText("Ticker for EQQQ");
    fireEvent.change(tickerInput, {
      target: { value: "EQQQ.L" },
    });
    fireEvent.change(screen.getByLabelText("Asset class for EQQQ"), {
      target: { value: "Equity ETF" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save EQQQ" }));

    await waitFor(() =>
      expect(api.updateInstrumentMarket).toHaveBeenCalledWith(7, {
        ticker: "EQQQ.L",
        asset_class: "Equity ETF",
        sector: null,
        region: null,
      }),
    );
  });
});
