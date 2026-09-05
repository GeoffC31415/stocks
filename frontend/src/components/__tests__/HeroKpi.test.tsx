import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeroKpi } from "../HeroKpi";

describe("HeroKpi", () => {
  it("renders the real balance immediately and updates without counting through invented values", () => {
    const view = render(<HeroKpi label="Portfolio value" value={4321} />);
    expect(screen.getByText("£4,321")).toBeInTheDocument();
    expect(screen.queryByText("£0")).not.toBeInTheDocument();
    view.rerender(<HeroKpi label="Portfolio value" value={1234} />);
    expect(screen.getByText("£1,234")).toBeInTheDocument();
  });
});
