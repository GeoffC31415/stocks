import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { it, expect, vi } from "vitest";
import { GroupsSection } from "../GroupsSection";
import { api, type Instrument } from "../../lib/api";

const mk = (id: number): Instrument =>
  ({
    id,
    identifier: `T${id}`,
    security_name: `Name ${id}`,
    account_name: "Acct",
    is_cash: false,
    group_ids: [1],
  }) as Instrument;

const group = {
  id: 1,
  name: "Core",
  target_allocation_pct: null,
  color: null,
  member_count: 2,
  total_value_gbp: 100,
};

const wrap = (node: ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>
);

it("focusing and leaving unchanged targets never writes portfolio metadata", async () => {
  const update = vi.spyOn(api, "updateGroup").mockResolvedValue({} as never);
  render(wrap(<GroupsSection groups={[group]} instruments={[]} byGroup={{}} />));
  const input = screen.getAllByPlaceholderText("Target %")[1];
  await act(async () => {
    fireEvent.focus(input);
    fireEvent.blur(input);
  });
  expect(update).not.toHaveBeenCalled();
});

it("recovers membership checkboxes when instruments arrive after groups", async () => {
  const a = mk(1);
  const b = mk(2);
  const { rerender } = render(wrap(<GroupsSection groups={[group]} instruments={[]} byGroup={{}} />));
  rerender(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
  const boxes = screen.getAllByRole("checkbox");
  expect(boxes).toHaveLength(2);
  boxes.forEach((box) => expect(box).toBeChecked());
  expect(screen.getByText(/2 members/)).toBeInTheDocument();
});

it("keeps the user's pending checkbox edits when membership data refreshes", async () => {
  const a = mk(1);
  const b = mk(2);
  const { rerender } = render(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
  fireEvent.click(screen.getAllByRole("checkbox")[1]);
  rerender(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
  const boxes = screen.getAllByRole("checkbox");
  expect(boxes[0]).toBeChecked();
  expect(boxes[1]).not.toBeChecked();
});
