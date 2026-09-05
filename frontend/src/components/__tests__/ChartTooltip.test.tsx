import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChartTooltip } from "../ChartTooltip";
import { ChartLegend } from "../ChartLegend";

describe("chart primitives", () => {
  it("keeps exact values and units while distinguishing missing data", () => {
    render(<ChartTooltip active label="Snapshot" payload={[
      { name: "Value", value: 1234.56, color: "#93c5fd" }, { name: "Missing", color: "#cbd5e1" },
    ]} />);
    expect(screen.getByText("£1,234.56")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("retains series names as a textual legend", () => {
    render(<ChartLegend payload={[{ value: "Value", color: "#93c5fd" }, { value: "Book cost", color: "#cbd5e1" }]} />);
    expect(screen.getByRole("list", { name: "Chart legend" })).toHaveTextContent("Book cost");
  });
});
