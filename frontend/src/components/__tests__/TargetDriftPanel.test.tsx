import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { Groups } from "../../routes/Groups";
vi.mock("../../lib/api", async (original) => ({...await original<typeof import("../../lib/api")>(), api:{getInstruments:vi.fn().mockResolvedValue([]),getGroups:vi.fn().mockResolvedValue([])}}));
afterEach(() => vi.unstubAllGlobals());
it("explains unavailable target sets and links to their existing editor", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>({status:"unavailable",account_name:null,invested_value_gbp:100,excluded_cash_gbp:25,tolerance_pp:2,reasons:["Set a target for every group"],groups:[],cash_policy:"Cash excluded"})}));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter><Groups /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", {name:"Target drift"})).toBeInTheDocument();
  expect(await screen.findByText("Set a target for every group")).toBeInTheDocument();
  expect(screen.getByRole("link", {name:"Resolve target configuration"})).toHaveAttribute("href", expect.stringContaining("/portfolio?tab=groups"));
});
