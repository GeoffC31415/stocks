import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const classifiedInstrument = {
  id: 8,
  account_name: "ISA",
  identifier: "AAPL",
  security_name: "Apple Inc.",
  is_cash: false,
  ticker: "AAPL",
  sector: "Technology",
  region: "US",
  asset_class: "Equity",
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
    vi.clearAllMocks();
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

  it("keeps failed rows highlighted and retryable, then reports a successful retry", async () => {
    vi.mocked(api.getInstruments).mockResolvedValue([classifiedInstrument]);
    vi.mocked(api.updateInstrumentMarket)
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({ ...classifiedInstrument, region: "USA" });
    renderQueue();

    fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
    fireEvent.change(await screen.findByLabelText("Region for AAPL"), { target: { value: "USA" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes (1)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("0 saved; 1 could not be saved");
    expect(screen.getByRole("row", { name: /AAPL/ })).toHaveTextContent("Changed");
    expect(screen.getByLabelText("Region for AAPL")).toHaveClass("border-amber-300/80");
    fireEvent.click(screen.getByRole("button", { name: "Save changes (1)" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 classification saved."));
    expect(api.updateInstrumentMarket).toHaveBeenCalledTimes(2);
  });

  it("keeps a non-standard Class value available to restore before saving", async () => {
    const customClassHolding = { ...classifiedInstrument, asset_class: "Investment Trust" } as Instrument;
    vi.mocked(api.getInstruments).mockResolvedValue([customClassHolding]);
    renderQueue();

    fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
    const classSelect = await screen.findByLabelText("Class for AAPL");
    fireEvent.change(classSelect, { target: { value: "Equity" } });
    expect(within(classSelect).getByRole("option", { name: "Investment Trust" })).toBeInTheDocument();
    fireEvent.change(classSelect, { target: { value: "Investment Trust" } });
    expect(screen.getByRole("button", { name: "Save changes (0)" })).toBeDisabled();
  });

  it("requires every classification cell before enabling bulk save", async () => {
    vi.mocked(api.getInstruments).mockResolvedValue([classifiedInstrument]);
    renderQueue();

    fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
    const classSelect = await screen.findByLabelText("Class for AAPL");
    expect(within(classSelect).queryByRole("option", { name: "Choose…" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sector for AAPL"), { target: { value: "  " } });

    expect(screen.getByRole("button", { name: "Save changes (1)" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Class, Sector, and Region are required");
    expect(api.updateInstrumentMarket).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Sector for AAPL"), { target: { value: "Technology" } });
    expect(screen.getByRole("button", { name: "Save changes (0)" })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the unmatched queue first and supports sorting and bulk-editing classifications", async () => {
    const secondHolding = {
      ...classifiedInstrument,
      id: 9,
      identifier: "MSFT",
      security_name: "Microsoft Corp.",
      sector: "Diverse",
      region: "USA",
    } as Instrument;
    vi.mocked(api.getInstruments).mockResolvedValue([incompleteInstrument, classifiedInstrument, secondHolding]);
    renderQueue();

    const queueHeading = await screen.findByRole("heading", { name: "Classification queue" });
    await screen.findByLabelText("Ticker for EQQQ");
    const editorHeading = screen.getByRole("heading", { name: "Edit existing classifications" });
    expect(queueHeading.compareDocumentPosition(editorHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const toggle = screen.getByRole("button", { name: "Show classification editor" });
    expect(toggle.querySelector("svg.lucide-chevron-down")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table", { name: "Existing classifications" })).not.toBeInTheDocument();
    fireEvent.click(toggle);

    const table = await screen.findByRole("table", { name: "Existing classifications" });
    for (const label of ["Holding", "Account", "Class", "Sector", "Region", "Status"]) {
      const button = within(table).getByRole("button", { name: new RegExp(`Sort by ${label}`) });
      fireEvent.click(button);
      expect(button.closest("th")?.getAttribute("aria-sort")).toMatch(/ascending|descending/);
    }
    const regionSort = within(table).getByRole("button", { name: /Sort by Region/ });

    fireEvent.click(regionSort);
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("AAPL");
    fireEvent.click(regionSort);
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("MSFT");

    fireEvent.change(screen.getByLabelText("Class for AAPL"), { target: { value: "Bond" } });
    fireEvent.change(screen.getByLabelText("Region for MSFT"), { target: { value: "United States" } });
    expect(within(table).getByRole("row", { name: /AAPL/ })).toHaveTextContent("Changed");
    expect(within(table).getByRole("row", { name: /MSFT/ })).toHaveTextContent("Changed");
    const aaplClass = screen.getByLabelText("Class for AAPL");
    const aaplSector = screen.getByLabelText("Sector for AAPL");
    expect(aaplClass).toHaveClass("border-amber-300/80");
    expect(aaplClass.closest("td")).toHaveClass("bg-amber-400/[0.09]");
    expect(aaplSector).not.toHaveClass("border-amber-300/80");
    expect(aaplSector.closest("td")).not.toHaveClass("bg-amber-400/[0.09]");
    expect(within(table).getByRole("row", { name: /AAPL/ })).not.toHaveClass("bg-amber-400/[0.04]");

    const saveButton = screen.getByRole("button", { name: "Save changes (2)" });
    expect(saveButton).toBeEnabled();
    expect(api.updateInstrumentMarket).not.toHaveBeenCalled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.updateInstrumentMarket).toHaveBeenCalledTimes(2);
      expect(api.updateInstrumentMarket).toHaveBeenCalledWith(8, { asset_class: "Bond" });
      expect(api.updateInstrumentMarket).toHaveBeenCalledWith(9, { region: "United States" });
    });
  });

});
