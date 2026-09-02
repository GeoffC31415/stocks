import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AllocationCategory } from "../../lib/allocationAnalysis";
import { AllocationDonut } from "../AllocationDonut";

const categories: AllocationCategory[] = [
  { label: "Equity ETF", value: 5400, weightPct: 54, count: 4 },
  { label: "Bond ETF", value: 2700, weightPct: 27, count: 2 },
  { label: "Cash", value: 900, weightPct: 9, count: 1 },
  { label: "Unclassified", value: 1000, weightPct: 10, count: 1 },
];

describe("AllocationDonut", () => {
  it("shows HHI with its label in the donut centre", () => {
    const { container } = render(
      <AllocationDonut categories={categories} totalValue={10000} hhi={3961} />,
    );
    const center = container.querySelector("[data-testid='allocation-donut-center']");
    expect(center?.textContent).toBe("3961");
    expect(center?.textContent).toContain("3961");
    expect(screen.getByText("HHI")).toBeInTheDocument();
  });

  it("keeps the Unclassified slice explicit in the legend table", () => {
    render(<AllocationDonut categories={categories} totalValue={10000} hhi={3961} />);
    const table = screen.getByRole("table", { name: /by asset class/i });
    expect(table).toBeInTheDocument();
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((row) =>
      row.textContent,
    );
    expect(rows).toContain("Unclassified 10.0% £1,000 · 1");
  });

  it("lists every category with its weight and value in the accessible table", () => {
    render(
      <AllocationDonut
        categories={categories}
        totalValue={10000}
        hhi={3961}
        dimension="sector"
      />,
    );
    const table = screen.getByRole("table", { name: /by sector/i });
    for (const category of categories) {
      const row = Array.from(table.querySelectorAll("tbody tr")).find(
        (tr) => tr.textContent?.startsWith(category.label),
      );
      expect(row?.textContent).toContain(`${category.weightPct.toFixed(1)}%`);
      expect(row?.textContent).toContain(`· ${category.count}`);
    }
  });

  it("handles an empty allocation without a donut", () => {
    render(<AllocationDonut categories={[]} totalValue={0} hhi={0} />);
    expect(screen.getByText("No positions")).toBeInTheDocument();
  });
});
