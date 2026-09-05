import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { IncomeAnalysisPanel } from "../IncomeAnalysisPanel";
vi.mock("../../lib/api",async original=>({...await original<typeof import("../../lib/api")>(),api:{getOrders:vi.fn().mockResolvedValue([]),getOrderPositions:vi.fn().mockResolvedValue([])}}));
afterEach(()=>vi.unstubAllGlobals());
it("renders backend calendar-matched totals and exact matching-purchase links without client aggregates",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({basis:"stored_import_classification",account_name:null,as_of:"2026-02-28",current_start:"2026-01-01",prior_start:"2025-01-01",prior_end:"2025-02-28",first_transaction_date:"2025-01-01",latest_transaction_date:"2026-02-28",completeness:"unknown",current_recorded_gbp:45,prior_recorded_gbp:30,change_gbp:15,current_count:2,prior_count:2,warnings:["Reinvestment proxy, not a dividend ledger.","Transaction completeness is unknown."],months:[{month:1,current_recorded_gbp:30,prior_recorded_gbp:20,current_count:1,prior_count:1}],drivers:[{key:"instrument:1",instrument_id:1,account_name:"ISA",name:"Core",holding_status:"current",current_recorded_gbp:30,prior_recorded_gbp:20,change_gbp:10,order_ids:[1,2]}]})}));
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={["/portfolio?tab=income&period=1Y"]}><IncomeAnalysisPanel/></MemoryRouter></QueryClientProvider>);
 expect(await screen.findByRole("table",{name:"Monthly recorded reinvestment proxy"})).toHaveTextContent("£30");
 expect(screen.getByText("Transaction completeness is unknown.")).toBeInTheDocument();
 const href=screen.getByRole("link",{name:"Core matching purchases"}).getAttribute("href")!;
 expect(href).toContain("kind=drip");expect(href).toContain("period=1Y");expect(href).toContain("account=ISA");expect(href).toContain("inst=1");
 expect(screen.getByText("2025-01-01 – 2025-02-28")).toBeInTheDocument();
});

it("labels order chips as a purchase proxy rather than proven dividends",async()=>{
 const {OrderRow}=await import('../OrderRow');
 render(<OrderRow order={{id:1,is_drip:true,side:'Buy',order_date:'2026-01-01',cost_proceeds_gbp:20,quantity:1} as import('../../lib/api').Order}/>);
 expect(screen.getByText('DRIP proxy')).toBeInTheDocument();
});
