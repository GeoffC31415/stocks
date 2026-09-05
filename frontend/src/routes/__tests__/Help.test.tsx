import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Help } from "../Help";

describe("Help", () => {
  it("preserves account and period on workspace deep links without leaking the Help tab", () => {
    render(<MemoryRouter initialEntries={["/help?account=ISA&period=1y&tab=old&inst=42"]}><Help /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "Open Portfolio" });
    const url = new URL(link.getAttribute("href")!, "https://local.test");
    expect(url.pathname).toBe("/portfolio");
    expect(url.searchParams.get("account")).toBe("ISA");
    expect(url.searchParams.get("period")).toBe("1y");
    expect(url.searchParams.get("inst")).toBe("42");
    expect(url.searchParams.get("tab")).toBe("performance");
  });
  it("answers analytical questions with scoped links and honest limitations", () => {
    render(<MemoryRouter initialEntries={["/help?account=HL&period=ytd"]}><Help /></MemoryRouter>);
    const questions = [
      ["What do I own now?", "Latest account snapshots", "/portfolio", "holdings"],
      ["Which return am I looking at?", "current-composition risk", "/portfolio", "performance"],
      ["Why does changing the period not change every view?", "own date filters", "/activity", "orders"],
      ["What explains the change in value?", "not pure price effects", "/activity", "changes"],
      ["When are two holdings the same security?", "IE0032077012", "/portfolio", "allocation"],
      ["Does a lower HHI mean I am diversified?", "fund overlap", "/portfolio", "allocation"],
      ["When can I compare my allocation with targets?", "100 ± 0.01", "/portfolio", "groups"],
      ["Does a contribution scenario move real money?", "real cash is unchanged", "/portfolio", "allocation"],
      ["Why is Income only a proxy?", "stored import classification", "/portfolio", "income"],
      ["How are Income periods and drivers compared?", "leap-day clamp", "/activity", "orders"],
      ["How do I repair low-confidence data?", "source account", "/data", "confidence"],
      ["Are risk forecasts and look-through ready?", "D01–D04", "/data", "settings"],
    ];
    for (const [title, qualification, path, tab] of questions) {
      const question = screen.getByText(title).closest("details")!;
      expect(question).toHaveTextContent(qualification);
      const url = new URL(question.querySelector("a")!.href);
      expect(url.pathname).toBe(path);
      expect(url.searchParams.get("tab")).toBe(tab);
      expect(url.searchParams.get("account")).toBe("HL");
      expect(url.searchParams.get("period")).toBe("ytd");
    }
    const purchases = new URL(screen.getByRole("link", { name: "Inspect matching purchases" }).getAttribute("href")!, "https://local.test");
    expect(purchases.searchParams.get("kind")).toBe("drip");
    expect(purchases.searchParams.get("offset")).toBe("0");
    expect(screen.queryByText(/Changing it recalculates DRIP/)).not.toBeInTheDocument();
    expect(screen.getByText(/null, not confirmed zero/)).toBeInTheDocument();
    expect(screen.getByText(/current, closed, and unlinked/)).toBeInTheDocument();
    for (const [label, tab] of [["Review import history", "imports"], ["Inspect position returns", "returns"], ["Repair classifications", "classifications"]]) {
      expect(screen.getByRole("link", { name: label }).getAttribute("href")).toContain(`tab=${tab}`);
    }
  });
  it("explains the main workflow, every workspace, and important metric limitations", () => {
    render(
      <MemoryRouter>
        <Help />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Help & site guide" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "A good routine" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Page-by-page guide" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Important concepts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Common questions" })).toBeInTheDocument();

    for (const name of ["Open Dashboard", "Open Portfolio", "Open Activity", "Open Tax", "Open Data"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }

    expect(screen.getAllByText(/Modified Dietz/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/product-level classifications/i)).toBeInTheDocument();
    expect(screen.getByText(/sales are treated as withdrawals/i)).toBeInTheDocument();
  });
});
