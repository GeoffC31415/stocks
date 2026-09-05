import { describe, expect, it } from "vitest";
import { categoryColor, chartTheme } from "../chartTheme";

describe("stable category colours", () => {
  it("does not recolour surviving categories on sorting/filtering", () => {
    const categories = ["Equity", "Bonds", "Other"];
    const original = Object.fromEntries(categories.map((name) => [name, categoryColor("asset_class", name)]));
    for (const name of [...categories].reverse().slice(1)) expect(categoryColor("asset_class", name)).toBe(original[name]);
  });
  it("always makes Unclassified explicit and includes dimension in identity", () => {
    expect(categoryColor("region", "Unclassified")).toBe(chartTheme.uncertainty);
    expect(categoryColor("asset_class", "Other")).not.toBe(categoryColor("region", "Other"));
  });
});
