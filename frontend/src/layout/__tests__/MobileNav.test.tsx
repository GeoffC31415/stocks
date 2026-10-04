import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { MobileNav } from "../MobileNav";

describe("MobileNav", () => {
  it("keeps primary destinations scoped without leaking a workspace tab", () => {
    render(
      <MemoryRouter initialEntries={["/portfolio?account=ISA&period=1Y&tab=income&inst=7"]}>
        <MobileNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Mobile" })).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    const urls = links.map(link => new URL(link.getAttribute("href")!, "https://local.test"));
    expect(urls.map(url => url.pathname)).toEqual(["/", "/portfolio", "/activity", "/tax", "/data", "/help"]);
    for (const url of urls) {
      expect(url.searchParams.get("account")).toBe("ISA");
      expect(url.searchParams.get("period")).toBe("1Y");
      expect(url.searchParams.get("tab")).toBeNull();
      expect(url.searchParams.get("inst")).toBe("7");
    }
  });
});
