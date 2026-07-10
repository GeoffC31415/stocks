import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Sidebar } from "../Sidebar";

const renderSidebar = () =>
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Sidebar />
    </MemoryRouter>,
  );

describe("Sidebar", () => {
  it("shows the five task-oriented destinations without admin categories", () => {
    renderSidebar();

    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Portfolio",
      "Activity",
      "Tax",
      "Data",
    ]);
    expect(screen.queryByText("Daily")).not.toBeInTheDocument();
    expect(screen.queryByText("Administration")).not.toBeInTheDocument();
  });
});
