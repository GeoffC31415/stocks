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
});
