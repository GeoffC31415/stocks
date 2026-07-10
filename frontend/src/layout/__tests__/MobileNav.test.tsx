import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { MobileNav } from "../MobileNav";

describe("MobileNav", () => {
  it("keeps every primary destination reachable on small screens", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <MobileNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Mobile" })).toBeInTheDocument();
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Portfolio",
      "Activity",
      "Tax",
      "Data",
    ]);
  });
});
