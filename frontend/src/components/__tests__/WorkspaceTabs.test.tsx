import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WorkspaceTabs } from "../WorkspaceTabs";

function LocationProbe() {
  return <output aria-label="location">{useLocation().search}</output>;
}

describe("WorkspaceTabs", () => {
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
