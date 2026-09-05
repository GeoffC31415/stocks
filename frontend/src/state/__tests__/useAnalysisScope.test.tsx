import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseAnalysisScope, useAnalysisScopeUrl } from "../useAnalysisScope";
import { scopedNavigationUrl } from "../../routing";
import { WorkspaceTabs } from "../../components/WorkspaceTabs";

const defaults = { account: "Saved", period: "1Y" as const };
function Probe() {
  const scope = useAnalysisScopeUrl(["ISA & pension", "Saved"]);
  const location = useLocation(), navigate = useNavigate();
  return <>
    <output aria-label="scope">{scope.account}/{scope.period}</output>
    <output aria-label="url">{location.search}</output>
    <button onClick={() => scope.setPeriod("1M")}>Month</button>
    <button onClick={() => scope.setAccount("Saved")}>Account</button>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate(1)}>Forward</button>
    <Link to={scopedNavigationUrl("/activity?tab=orders", location.search)}>Orders</Link>
    <WorkspaceTabs label="Views" tabs={[{ key: "holdings", label: "Holdings" }, { key: "income", label: "Income" }]} />
  </>;
}

describe("analysis scope", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    });
  });
  afterEach(() => vi.unstubAllGlobals());
  it("gives exact URL scope precedence over stored defaults", () => {
    const result = parseAnalysisScope(new URLSearchParams("account=ISA+%26+pension&period=YTD&inst=0007"), defaults, ["ISA & pension"]);
    expect(result).toEqual({ account: "ISA & pension", period: "YTD", errors: [] });
  });
  it.each(["period=BAD", "period=", "account=", "account=Unknown", "account=ISA%0A",
    "period=ALL&period=1M", "start=2026-02-30", "start=2026-03-01&end=2026-01-01", "end=2026-01-01"])("rejects malformed or unsupported scope: %s", (query) => {
    expect(parseAnalysisScope(new URLSearchParams(query), defaults, ["Saved"]).errors.length).toBeGreaterThan(0);
  });
  it("persists period/account through workspace tabs and Back/Forward without losing identifiers", async () => {
    localStorage.setItem("portfolio.accountFilter", "Saved");
    localStorage.setItem("portfolio.analysisPeriod", "1Y");
    render(<MemoryRouter initialEntries={["/portfolio?account=ISA+%26+pension&period=YTD&inst=0007&q=long+name&type=buy"]}><Probe /></MemoryRouter>);
    expect(screen.getByLabelText("scope")).toHaveTextContent("ISA & pension/YTD");
    fireEvent.click(screen.getByText("Month"));
    fireEvent.click(screen.getByRole("tab", { name: "Income" }));
    expect(screen.getByLabelText("url")).toHaveTextContent("period=1M");
    fireEvent.click(screen.getByText("Orders"));
    expect(screen.getByLabelText("url")).toHaveTextContent("inst=0007&q=long+name&type=buy&tab=orders");
    fireEvent.click(screen.getByText("Back"));
    expect(screen.getByLabelText("url")).toHaveTextContent("tab=income");
    fireEvent.click(screen.getByText("Back"));
    fireEvent.click(screen.getByText("Back"));
    expect(screen.getByLabelText("scope")).toHaveTextContent("ISA & pension/YTD");
    fireEvent.click(screen.getByText("Forward"));
    expect(screen.getByLabelText("scope")).toHaveTextContent("ISA & pension/1M");
    fireEvent.click(screen.getByText("Account"));
    await waitFor(() => expect(localStorage.getItem("portfolio.accountFilter")).toBe("Saved"));
  });
  it("materialises stored defaults in a legacy unscoped URL without changing inst", async () => {
    localStorage.setItem("portfolio.accountFilter", "Saved");
    localStorage.setItem("portfolio.analysisPeriod", "6M");
    render(<MemoryRouter initialEntries={["/holdings?inst=0007"]}><Probe /></MemoryRouter>);
    await waitFor(() => expect(screen.getByLabelText("url")).toHaveTextContent("inst=0007&account=Saved&period=6M"));
  });
});
