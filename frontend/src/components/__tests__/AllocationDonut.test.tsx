import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AllocationCategory } from "../../lib/api";
import { AllocationDonut } from "../AllocationDonut";

const categories: AllocationCategory[] = [
  { label: "Equity ETF", value: 5400, weightPct: 54, count: 4 },
  { label: "Bond ETF", value: 2700, weightPct: 27, count: 2 },
  { label: "Property", value: 900, weightPct: 9, count: 1 },
  { label: "Unclassified", value: 1000, weightPct: 10, count: 1 },
];

describe("AllocationDonut", () => {
  it("uses invested value in the centre instead of repeating a technical HHI headline", () => {
    render(<AllocationDonut categories={categories} totalValue={10000} />);
    expect(screen.getByTestId("allocation-donut-center")).toHaveTextContent("£10k");
    expect(screen.getByText("Invested")).toBeInTheDocument();
    expect(screen.queryByText("HHI")).not.toBeInTheDocument();
  });
  it("keeps every category explicit in an accessible table with meaningful headings", () => {
    render(<AllocationDonut categories={categories} totalValue={10000} dimension="sector" />);
    const table = screen.getByRole("table", { name: "By sector" });
    expect(within(table).getByRole("columnheader", { name: "Sector" })).toBeInTheDocument();
    for (const category of categories) {
      const row = within(table).getByRole("rowheader", { name: category.label }).closest("tr")!;
      expect(within(row).getByText(`${category.weightPct.toFixed(1)}%`)).toBeInTheDocument();
      expect(within(row).getByText(String(category.count))).toBeInTheDocument();
    }
  });
  it("makes exact values reachable by a button rather than hover alone", () => {
    render(<AllocationDonut categories={categories} totalValue={10000} dimension="currency" />);
    expect(screen.getByRole("columnheader", { name: "Source currency" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show exact values" }));
    expect(screen.getByText("£5,400.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show rounded values" })).toHaveAttribute("aria-pressed", "true");
  });
  it("handles empty allocation without a donut", () => {
    render(<AllocationDonut categories={[]} totalValue={0} />);
    expect(screen.getByText("No positions")).toBeInTheDocument();
  });
});
