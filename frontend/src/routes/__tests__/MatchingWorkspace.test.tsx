import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api, type MatchSummary } from "../../lib/api";
import { MatchingWorkspace } from "../MatchingWorkspace";

const healthy: MatchSummary = {
  orders_total: 397,
  orders_matched: 397,
  orders_unmatched: 0,
  orders_auto_high: 350,
  orders_auto_review: 0,
  orders_manual: 47,
  orders_ignored: 0,
  orders_legacy: 0,
  unmatched_groups: 0,
  instruments_with_reconciliation_issues: 0,
};

vi.mock("../MatchingAdmin", () => ({
  MatchingAdmin: () => <div>Advanced matching admin</div>,
}));

describe("MatchingWorkspace", () => {
  it("keeps healthy matching quiet until advanced tools are requested", async () => {
    vi.spyOn(api, "getMatchingSummary").mockResolvedValue(healthy);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MatchingWorkspace />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Matching is healthy")).toBeInTheDocument();
    expect(screen.queryByText("Advanced matching admin")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open advanced matching tools" }));
    expect(screen.getByText("Advanced matching admin")).toBeInTheDocument();
  });
});
