import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "../MetricCard";
import { SectionHeader } from "../SectionHeader";

describe("analytical primitives", () => {
  it("names a metric and keeps its basis accessible alongside the exact value", () => {
    render(<MetricCard label="Portfolio value" value="£123.45" description="Latest snapshot" emphasis />);
    const card = screen.getByRole("article", { name: "Portfolio value" });
    expect(within(card).getByText("£123.45")).toBeInTheDocument();
    expect(within(card).getByText("Latest snapshot")).toBeInTheDocument();
  });
  it("preserves signed text rather than using colour as the only signal", () => {
    render(<MetricCard label="Investment return" value="−3.5%" tone="negative" description="1 Jan – 1 Feb" />);
    expect(screen.getByText("−3.5%")).toBeInTheDocument();
    expect(screen.getByText("1 Jan – 1 Feb")).toBeInTheDocument();
  });
  it("keeps section actions associated with a real heading", () => {
    render(<SectionHeader title="Performance" description="Snapshot-derived" actions={<button>Change period</button>} />);
    expect(screen.getByRole("heading", { level: 2, name: "Performance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change period" })).toBeInTheDocument();
  });
});
