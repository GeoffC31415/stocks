import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricInfo } from "../MetricInfo";

describe("MetricInfo", () => {
  it("opens a named definition with period context and restores focus on Escape", () => {
    render(<MetricInfo label="Snapshot return" topic="totalReturn" context="1 Jan – 1 Feb" />);
    const trigger = screen.getByRole("button", { name: "About Snapshot return" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Snapshot return definition" });
    expect(dialog).toHaveFocus();
    expect(dialog).toHaveTextContent("1 Jan – 1 Feb");
    expect(dialog).toHaveTextContent("order-derived assumptions");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
  it("closes on outside pointer activation and explicit dismissal", () => {
    render(<MetricInfo label="Drawdown" topic="maxDrawdown" />);
    const trigger = screen.getByRole("button", { name: "About Drawdown" });
    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Close definition" }));
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
