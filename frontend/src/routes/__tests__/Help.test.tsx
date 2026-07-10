import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Help } from "../Help";

describe("Help", () => {
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
