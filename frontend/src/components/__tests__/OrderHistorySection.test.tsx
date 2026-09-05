import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { OrderHistorySection } from "../OrderHistorySection";
import type { OrderPage } from "../../lib/orderPageApi";

it("renders backend total reasons rather than assuming missing amounts", () => {
  const page = { items: [], total_count: 0, offset: 0, limit: 100, has_more: false,
    totals: { buy_gbp: null, sell_gbp: 0, drip_gbp: 0 },
    totals_reasons: { buy_gbp: "non_finite_total" as const, sell_gbp: null, drip_gbp: null }, classification_basis: "Stored" };
  render(<OrderHistorySection page={page} pending={false} error={false} params={new URLSearchParams()} onChange={vi.fn()} onRetry={vi.fn()} />);
  expect(screen.getByText(/Full-filter totals/)).toHaveTextContent("Unavailable (non-finite total)");
});

it.each([
  ["Next page", 0, 100, true],
  ["Next page", 100, 200, false],
  ["Previous page", 100, 0, true],
] as const)("restores results focus after delayed %s from %s to %s", (name, offset, nextOffset, hasMore) => {
  const page: OrderPage = { items: [], total_count: 205, offset, limit: 100, has_more: true,
    totals: { buy_gbp: 25, sell_gbp: 0, drip_gbp: 0 }, totals_reasons: { buy_gbp: null, sell_gbp: null, drip_gbp: null }, classification_basis: "Stored" };
  const props = { page, pending: false, error: false, params: new URLSearchParams(), onChange: vi.fn(), onRetry: vi.fn() };
  const { rerender } = render(<OrderHistorySection {...props} />);
  const button = screen.getByRole("button", { name });
  button.focus();
  fireEvent.click(button);
  expect(props.onChange).toHaveBeenCalledWith("offset", String(nextOffset));
  rerender(<OrderHistorySection {...props} pending />);
  expect(screen.queryByText(/Full-filter totals/)).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Order results" })).not.toBeInTheDocument();
  rerender(<OrderHistorySection {...props} page={{ ...page, offset: nextOffset, has_more: hasMore }} />);
  expect(screen.getByRole("region", { name: "Order results" })).toHaveFocus();
  if (!hasMore) expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
});
