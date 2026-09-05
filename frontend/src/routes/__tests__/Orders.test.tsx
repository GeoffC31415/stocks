import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { Orders } from "../Orders";

vi.mock("../../state/usePreferences", () => ({ usePreferences: () => ({ dripThreshold: 1000, accountFilter: "all" }) }));
vi.mock("../../components/MatchingWarningBanner", () => ({ MatchingWarningBanner: () => null }));
afterEach(() => vi.unstubAllGlobals());

function SwitchAccount() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/activity?tab=orders&account=SIPP&offset=100")}>Switch account</button>;
}

it("hides previous account rows through pending, error and retry", async () => {
  const payload = { items: [{ id: 1, security_name: "ISA-only holding", side: "Buy", order_date: "2026-01-01", cost_proceeds_gbp: 10 }],
    offset: 100, limit: 100, total_count: 101, has_more: false, totals: { buy_gbp: 10, sell_gbp: 0, drip_gbp: 0 } };
  let rejectRequest: (error: Error) => void = () => {};
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => payload })
    .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRequest = reject; }))
    .mockResolvedValue({ ok: true, json: async () => ({ ...payload, items: [], offset: 0, total_count: 0 }) });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/activity?account=ISA&offset=100"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SwitchAccount /><Orders /></QueryClientProvider></MemoryRouter>);
  expect(await screen.findByText("ISA-only holding")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Switch account"));
  expect(screen.queryByText("ISA-only holding")).not.toBeInTheDocument();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  const query = new URL(String(fetcher.mock.calls[1][0]), "http://test").searchParams;
  expect(query.get("account_name")).toBe("SIPP");
  expect(query.get("offset")).toBe("0");
  rejectRequest(new Error("offline"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load");
  expect(screen.queryByText("ISA-only holding")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Retry"));
  expect(await screen.findByText(/of 0 matching transactions/)).toBeInTheDocument();
});

it("pages server results and resets URL filters without displaying stale rows", async () => {
  const fetcher = vi.fn().mockImplementation(async (url: string) => {
    const params = new URL(url, "http://test").searchParams;
    const offset = Number(params.get("offset") || 0);
    return { ok: true, json: async () => ({ items: [], total_count: 105, offset, limit: 100,
      has_more: offset === 0, totals: { buy_gbp: 210000, sell_gbp: 0, drip_gbp: 0 } }) };
  });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/activity?tab=orders&account=ISA"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Orders /></QueryClientProvider></MemoryRouter>);
  expect(await screen.findByText(/of 105 matching transactions/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("offset=100"))).toBe(true));
  fireEvent.change(screen.getByRole("textbox", { name: "Search orders" }), { target: { value: "Target" } });
  await waitFor(() => {
    const url = new URL(String(fetcher.mock.calls[fetcher.mock.calls.length - 1]?.[0]), "http://test");
    expect(url.pathname).toBe("/api/orders/page");
    expect(url.searchParams.get("search")).toBe("Target");
    expect(url.searchParams.get("offset")).toBe("0");
    expect(url.searchParams.get("account_name")).toBe("ISA");
  });
  expect(screen.getByText(/Full-filter totals/)).toBeInTheDocument();
  expect(screen.getByText(/Reinvestment proxy, not dividend ledger/)).toBeInTheDocument();
});
