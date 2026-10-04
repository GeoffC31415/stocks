import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WorkspaceTabs } from "../WorkspaceTabs";

function LocationProbe() {
  return <output aria-label="location">{useLocation().search}</output>;
}

describe("WorkspaceTabs", () => {
  it('validates unknown tabs and supplies roving focus and panel relationships', () => {
    render(<MemoryRouter initialEntries={['/?tab=unknown&account=ISA&period=1Y']}><WorkspaceTabs label="Portfolio views" tabs={[{key:'holdings',label:'Holdings'},{key:'returns',label:'Returns'}]} /><LocationProbe /></MemoryRouter>);
    const first=screen.getByRole('tab',{name:'Holdings'}), second=screen.getByRole('tab',{name:'Returns'});
    expect(first).toHaveAttribute('aria-selected','true');
    expect(first).toHaveAttribute('tabindex','0'); expect(second).toHaveAttribute('tabindex','-1');
    expect(first).toHaveAttribute('aria-controls','workspace-panel');
    expect(first.id).toBe('workspace-tab-holdings');
    expect(screen.getByLabelText('location')).toHaveTextContent('tab=holdings&account=ISA&period=1Y');
    first.focus(); fireEvent.keyDown(first,{key:'End'}); expect(second).toHaveFocus();
    fireEvent.keyDown(second,{key:'ArrowRight'}); expect(first).toHaveFocus();
  });
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

});
