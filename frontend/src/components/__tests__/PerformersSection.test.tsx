import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Instrument } from "../../lib/api";
import { PerformersSection } from "../PerformersSection";

const instrument = (id: number, name: string, change: number): Instrument =>
  ({ id, security_name: name, latest_pct_change: change }) as Instrument;

describe("PerformersSection", () => {
  it("describes the lowest positive returns without implying a loss", () => {
    render(
      <PerformersSection
        worst={[instrument(1, "Lower positive return", 2)]}
        best={[instrument(2, "Higher return", 20)]}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Lowest returns" })).toBeInTheDocument();
    expect(screen.getByText("2.00%")).toHaveClass("text-amber-300");
  });
});
