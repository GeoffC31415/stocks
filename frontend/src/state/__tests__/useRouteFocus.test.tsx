import { useRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useRouteFocus } from "../useRouteFocus";

function Workspace() {
  const location = useLocation(), navigate = useNavigate();
  const root = useRef<HTMLElement>(null);
  useRouteFocus(root, location.pathname);
  return <><button onClick={() => navigate("/detail")}>Forward</button>
    <button onClick={() => navigate(-1)}>Back</button>
    <input aria-label="Investigation search" onChange={() => navigate("/typed")} />
    <main ref={root}><h1>{location.pathname}</h1></main></>;
}

describe("route focus", () => {
  it("focuses the new heading on forward navigation, not on back", () => {
    render(<MemoryRouter><Workspace /></MemoryRouter>);
    const forward = screen.getByRole("button", { name: "Forward" });
    forward.focus();
    fireEvent.click(forward);
    expect(screen.getByRole("heading", { name: "/detail" })).toHaveFocus();
    const back = screen.getByRole("button", { name: "Back" });
    back.focus();
    fireEvent.click(back);
    expect(back).toHaveFocus();
  });
  it("does not steal active text-input focus", () => {
    render(<MemoryRouter><Workspace /></MemoryRouter>);
    const input = screen.getByRole("textbox");
    input.focus();
    fireEvent.change(input, { target: { value: "Asset" } });
    expect(input).toHaveFocus();
    expect(screen.getByRole("heading", { name: "/typed" })).toBeInTheDocument();
  });
});
