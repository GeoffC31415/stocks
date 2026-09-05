import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WorkspaceTabs } from "../WorkspaceTabs";

function LocationProbe() {
  return <output aria-label="location">{useLocation().search}</output>;
}

describe("WorkspaceTabs", () => {
  it("moves keyboard focus with arrow keys without losing investigation parameters", () => {
    render(<MemoryRouter initialEntries={["/portfolio?tab=holdings&account=ISA&inst=7"]}>
      <WorkspaceTabs label="Portfolio views" tabs={[
        { key: "holdings", label: "Holdings" }, { key: "returns", label: "Returns" },
      ]} /><LocationProbe />
    </MemoryRouter>);
    const first = screen.getByRole("tab", { name: "Holdings" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Returns" })).toHaveFocus();
    expect(screen.getByLabelText("location")).toHaveTextContent("tab=returns&account=ISA&inst=7");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Returns" }), { key: "Home" });
    expect(first).toHaveFocus();
  });

  it("stores the selected workspace view in the URL", () => {
    render(
      <MemoryRouter initialEntries={["/portfolio?tab=holdings"]}>
        <WorkspaceTabs
          label="Portfolio views"
          tabs={[
            { key: "holdings", label: "Holdings" },
            { key: "returns", label: "Returns" },
          ]}
        />
        <LocationProbe />
      </MemoryRouter>,
    );

    expect(screen.getByRole("tab", { name: "Holdings" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Returns" }));
    expect(screen.getByLabelText("location")).toHaveTextContent("tab=returns");
  });
});
