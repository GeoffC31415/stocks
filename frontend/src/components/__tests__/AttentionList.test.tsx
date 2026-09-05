import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AttentionItem } from "../../lib/dataQualityApi";
import { AttentionList } from "../AttentionList";

const reminder: AttentionItem = { id: "stale", title: "Old snapshot", category: "rule", severity: "warning",
  evidence: ["Valuation on 2026-01-01"], evidence_key: "first", dismissible: true,
  action_href: "/data?tab=import&account=ISA&period=YTD", account_name: "ISA", period: "YTD" };
beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value) });
});
afterEach(() => vi.unstubAllGlobals());

it("dismisses only unchanged evidence, restores reminders and preserves the repair scope", () => {
  const view = render(<AttentionList items={[reminder]} />);
  expect(screen.getByRole("link")).toHaveAttribute("href", reminder.action_href);
  fireEvent.click(screen.getByRole("button", { name: "Dismiss unchanged reminder" }));
  expect(screen.queryByText("Old snapshot")).not.toBeInTheDocument();
  view.rerender(<AttentionList items={[{ ...reminder, evidence_key: "changed" }]} />);
  expect(screen.getByText("Old snapshot")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss unchanged reminder" }));
  fireEvent.click(screen.getByRole("button", { name: "Restore reminders" }));
  expect(screen.getByText("Old snapshot")).toBeInTheDocument();
});

it("cannot hide a critical calculation failure even with stale dismissal storage or a bad dismissible flag", () => {
  localStorage.setItem("portfolio.attentionDismissals.v1", JSON.stringify(["first"]));
  render(<AttentionList items={[{ ...reminder, severity: "critical", title: "Broken calculation" }]} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Broken calculation");
  expect(screen.queryByRole("button", { name: "Dismiss unchanged reminder" })).not.toBeInTheDocument();
});
