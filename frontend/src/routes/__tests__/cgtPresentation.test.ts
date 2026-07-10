import { describe, expect, it } from "vitest";
import { latestTaxYear, selectTaxYear } from "../cgtPresentation";

describe("latestTaxYear", () => {
  it("returns the latest available tax year even when rows are unsorted", () => {
    expect(
      latestTaxYear([
        { tax_year: "2025-26" },
        { tax_year: "2023-24" },
        { tax_year: "2026-27" },
        { tax_year: "2024-25" },
      ]),
    ).toBe("2026-27");
  });

  it("returns null when no tax years are available", () => {
    expect(latestTaxYear([])).toBeNull();
  });
});

describe("selectTaxYear", () => {
  const rows = [
    { tax_year: "2023-24", taxable_gain: 7000 },
    { tax_year: "2024-25", taxable_gain: 4000 },
  ];

  it("returns only the explicitly selected tax year's row", () => {
    expect(selectTaxYear(rows, "2023-24")?.taxable_gain).toBe(7000);
  });

  it("defaults to the latest row when no valid selection exists", () => {
    expect(selectTaxYear(rows, null)?.taxable_gain).toBe(4000);
    expect(selectTaxYear(rows, "2022-23")?.taxable_gain).toBe(4000);
  });
});
