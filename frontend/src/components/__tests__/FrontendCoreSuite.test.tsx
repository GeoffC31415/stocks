import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HeroKpi } from "../HeroKpi";
import { ChartTooltip } from "../ChartTooltip";
import { api, type GroupPerformance, type Instrument, type PortfolioReturnSummary, type SnapshotAttribution } from "../../lib/api";
import { PortfolioReturnCard } from "../PortfolioReturnCard";
import { PerformersSection } from "../PerformersSection";
import { Link, MemoryRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { WorkspaceTabs } from "../WorkspaceTabs";
import { type AttentionItem } from "../../lib/dataQualityApi";
import { AttentionList } from "../AttentionList";
import { MetricInfo } from "../MetricInfo";
import { AnalysisSettings } from "../AnalysisSettings";
import { PreferencesContext } from "../../state/usePreferences";
import { InlineSparkline } from "../InlineSparkline";
import { SyncEvidence } from "../SyncEvidence";
import publicReport from "./fixtures/public-sync-v2.json";
import { MobileNav } from "../../layout/MobileNav";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Diff } from "../../routes/Diff";
import { Help } from "../../routes/Help";
import { ImportActivity } from "../../routes/ImportActivity";
import { timelineApi } from "../../lib/timelineApi";
import { TimelineSourceView } from "../../routes/TimelineSourceView";
import { parseAnalysisScope, useAnalysisScopeUrl } from "../../state/useAnalysisScope";
import { scopedNavigationUrl } from "../../routing";
import { useRef } from "react";
import { useRouteFocus } from "../../state/useRouteFocus";
import { HoldingsTable } from "../HoldingsTable";
import { type AllocationTargets } from "../../lib/allocationTargetsApi";
import { ImportPanel } from "../ImportPanel";
import { ClassificationQueue } from "../ClassificationQueue";
import { ContributionDetails } from "../ContributionDetails";
import { GroupPerformancePanel } from "../GroupPerformancePanel";
import { IncomeAnalysisPanel } from "../IncomeAnalysisPanel";
import { Groups } from "../../routes/Groups";
import { TargetDriftPanel } from "../TargetDriftPanel";
import { AllocationScenarioPanel } from "../AllocationScenarioPanel";

describe("CoreAndRoutes", () => {
  describe("CoreComponents", () => {
    describe("HeroKpi", () => {
      describe("HeroKpi", () => {
        it("renders the real balance immediately and updates without counting through invented values", () => {
          const view = render(<HeroKpi label="Portfolio value" value={4321} />);
          expect(screen.getByText("£4,321")).toBeInTheDocument();
          expect(screen.queryByText("—")).not.toBeInTheDocument();
          expect(screen.queryByText("£0")).not.toBeInTheDocument();
          view.rerender(<HeroKpi label="Portfolio value" value={1234} />);
          expect(screen.getByText("£1,234")).toBeInTheDocument();
        });
      });
    });

    describe("ChartTooltip", () => {
      describe("chart primitives", () => {
        it("keeps exact values and units while distinguishing missing data", () => {
          render(<ChartTooltip active label="Snapshot" payload={[
            { name: "Value", value: 1234.56, color: "#93c5fd" }, { name: "Missing", color: "#cbd5e1" },
          ]} />);
          expect(screen.getByText("£1,234.56")).toBeInTheDocument();
          expect(screen.getByText("—")).toBeInTheDocument();
        });
      });
    });

    describe("PortfolioReturnCard", () => {
      const summary: PortfolioReturnSummary = {
        period_start: "2025-01-01",
        period_end: "2025-12-31",
        start_value_gbp: 1000,
        end_value_gbp: 1200,
        contributions_gbp: 100,
        withdrawals_gbp: 0,
        net_external_flow_gbp: 100,
        absolute_gain_after_flows_gbp: 100,
        modified_dietz_return_pct: 9.52,
        annualised_return_pct: null,
        method: "Modified Dietz",
        notes: [],
      };

      describe("PortfolioReturnCard", () => {
        it("shows the Modified Dietz return with method and period context", () => {
          render(<PortfolioReturnCard summary={summary} />);

          expect(screen.getByText("Estimated money-weighted return")).toBeInTheDocument();
          expect(screen.getByText("+9.52%")).toBeInTheDocument();
          expect(screen.getByText(/Cumulative, not annualised/)).toBeInTheDocument();
          expect(screen.getByText(/Modified Dietz/)).toBeInTheDocument();
          expect(screen.getByText(/1 Jan 2025.*31 Dec 2025/)).toBeInTheDocument();
        });

        it("shows a clear unavailable state instead of inventing a return", () => {
          render(
            <PortfolioReturnCard
              summary={{
                ...summary,
                period_start: null,
                period_end: null,
                modified_dietz_return_pct: null,
                notes: ["At least two snapshot dates are required to calculate a return."],
              }}
            />,
          );

          expect(screen.getByText("Unavailable")).toBeInTheDocument();
          expect(screen.getByText(/At least two snapshot dates/)).toBeInTheDocument();
        });
      });
    });

    describe("PerformersSection", () => {
      const instrument = (id: number, name: string, change: number): Instrument =>
        ({ id, security_name: name, latest_pct_change: change }) as Instrument;

      describe("PerformersSection", () => {
        it("describes the lowest positive returns without implying a loss", () => {
          render(
            <PerformersSection
              worst={[instrument(1, "Lower positive return", 2)]}
              best={[instrument(2, "Higher return", 20)]}
              onSelect={vi.fn()}
            />,
          );

          expect(screen.getByRole("heading", { name: "Lowest returns" })).toBeInTheDocument();
          expect(screen.getByText("2.00%")).toHaveClass("text-amber-300");
        });
      });
    });

    describe("WorkspaceTabs", () => {
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
    });

    describe("AttentionList", () => {
      const reminder: AttentionItem = { id: "stale", title: "Old snapshot", category: "rule", severity: "warning",
        evidence: ["Valuation on 2026-01-01"], evidence_key: "first", dismissible: true,
        action_href: "/data?tab=import&account=ISA&period=YTD", account_name: "ISA", period: "YTD" };
      beforeEach(() => {
        const values = new Map<string, string>();
        vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
          setItem: (key: string, value: string) => values.set(key, value) });
      });
      afterEach(() => vi.unstubAllGlobals());

      it("dismisses only unchanged evidence, restores reminders and preserves the repair scope", () => {
        const view = render(<AttentionList items={[reminder]} />);
        expect(screen.getByRole("link")).toHaveAttribute("href", reminder.action_href);
        fireEvent.click(screen.getByRole("button", { name: "Dismiss unchanged reminder" }));
        expect(screen.queryByText("Old snapshot")).not.toBeInTheDocument();
        view.rerender(<AttentionList items={[{ ...reminder, evidence_key: "changed" }]} />);
        expect(screen.getByText("Old snapshot")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Dismiss unchanged reminder" }));
        fireEvent.click(screen.getByRole("button", { name: "Restore reminders" }));
        expect(screen.getByText("Old snapshot")).toBeInTheDocument();
      });

      it("cannot hide a critical calculation failure even with stale dismissal storage or a bad dismissible flag", () => {
        localStorage.setItem("portfolio.attentionDismissals.v1", JSON.stringify(["first"]));
        render(<AttentionList items={[{ ...reminder, severity: "critical", title: "Broken calculation" }]} />);
        expect(screen.getByRole("alert")).toHaveTextContent("Broken calculation");
        expect(screen.queryByRole("button", { name: "Dismiss unchanged reminder" })).not.toBeInTheDocument();
      });
    });

    describe("MetricInfo", () => {
      describe("MetricInfo", () => {
        it("opens a named definition with period context and restores focus on Escape", () => {
          render(<MetricInfo label="Snapshot return" topic="totalReturn" context="1 Jan – 1 Feb" />);
          const trigger = screen.getByRole("button", { name: "About Snapshot return" });
          fireEvent.click(trigger);
          const dialog = screen.getByRole("dialog", { name: "Snapshot return definition" });
          expect(dialog).toHaveFocus();
          expect(dialog).toHaveTextContent("1 Jan – 1 Feb");
          expect(dialog).toHaveTextContent("order-derived assumptions");
          fireEvent.keyDown(document, { key: "Escape" });
          expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
          expect(trigger).toHaveFocus();
          expect(trigger).toHaveAttribute("aria-expanded", "false");
        });
        it("closes on outside pointer activation and explicit dismissal", () => {
          render(<MetricInfo label="Drawdown" topic="maxDrawdown" />);
          const trigger = screen.getByRole("button", { name: "About Drawdown" });
          fireEvent.click(trigger);
          fireEvent.pointerDown(document.body);
          expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
          fireEvent.click(trigger);
          fireEvent.click(screen.getByRole("button", { name: "Close definition" }));
          expect(trigger).toHaveFocus();
          expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        });
      });
    });

    describe("AnalysisSettings", () => {
      it("explains the heuristic and changes only the local threshold, preserving scope in the Income link", () => {
        const setDripThreshold = vi.fn();
        render(<MemoryRouter initialEntries={["/data?tab=settings&account=ISA&period=YTD"]}>
          <PreferencesContext.Provider value={{ dripThreshold: 1000, setDripThreshold, accountFilter: "ISA", setAccountFilter: vi.fn() }}>
            <AnalysisSettings />
          </PreferencesContext.Provider>
        </MemoryRouter>);
        expect(screen.getByText(/not proven dividends/)).toBeInTheDocument();
        fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "250.50" } });
        fireEvent.click(screen.getByRole("button", { name: "Apply" }));
        expect(setDripThreshold).toHaveBeenCalledWith(250.5);
        expect(screen.getByRole("link", { name: "View Income proxy" })).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&tab=income");
      });
    });

    describe("InlineSparkline", () => {
      describe("InlineSparkline", () => {
        it("renders an em dash when fewer than two finite points are provided", () => {
          const { container } = render(<InlineSparkline values={[100]} label="VWRL trend" />);
          expect(container.textContent).toBe("—");
          expect(container.querySelector("svg")).toBeNull();
        });

        it("renders an accessible SVG polyline colored by net direction", () => {
          render(<InlineSparkline values={[100, 104, 102, 110]} label="VWRL trend" />);
          const svg = screen.getByRole("img", { name: "VWRL trend" });
          const polyline = svg.querySelector("polyline");
          expect(polyline).not.toBeNull();
          expect(polyline?.getAttribute("stroke")).toBe("#34d399");
        });

        it("uses negative stroke when ending below start", () => {
          render(<InlineSparkline values={[110, 105, 98]} label="AZN trend" />);
          const svg = screen.getByRole("img", { name: "AZN trend" });
          expect(svg.querySelector("polyline")?.getAttribute("stroke")).toBe("#fb7185");
        });
      });
    });

    describe("SyncEvidence", () => {
      it('renders serialized real public-report evidence without confusing a failed attempt with retained verification', () => {
       render(<SyncEvidence report={publicReport} />);
       expect(screen.getByText('Refresh outcome: partial')).not.toHaveClass('text-pos');
       expect(screen.getByText('Trading 212 / holdings: failed')).toBeInTheDocument();
       expect(screen.getByText('Checked: 2026-09-01T18:30:00+00:00')).toBeInTheDocument();
       expect(screen.getByText('Valuation: 2026-09-01')).toBeInTheDocument();
       expect(screen.getByText('Attempt: 2026-09-29T18:29:00+00:00')).toBeInTheDocument();
       expect(screen.getByText('Coverage: partial')).toBeInTheDocument();
       expect(screen.getByText('Reason: provider_failed')).toBeInTheDocument();
       expect(screen.getByText('Action: retry')).toBeInTheDocument();
       expect(screen.getByText(/retained verified observation/)).toBeInTheDocument();
      });
      // Partial/no-op appear in serialized-report and confidence integration tests.
      // Success/failure endpoints guard against inferring success from legacy ok:true.
      it.each(['complete','failed'] as const)('recognizes authoritative %s outcome without inferring green success', outcome => {
       render(<SyncEvidence report={{outcome,ok:true}} />);
       expect(screen.getByText(`Refresh outcome: ${outcome}`)).not.toHaveClass('text-pos');
      });
      it('uses sanitized step sections when freshness is absent', () => {
       const {freshness: _freshness, ...stepReport} = publicReport;
       render(<SyncEvidence report={stepReport} />);
       expect(screen.getByText('Trading 212 / holdings: failed')).toBeInTheDocument();
       expect(screen.getByText('Checked: 2026-09-01T18:30:00+00:00')).toBeInTheDocument();
      });
      it('keeps authoritative freshness ahead of duplicate current-run step evidence', () => {
       render(<SyncEvidence report={{...publicReport, steps:[{name:'Trading 212',status:'ok',detail:null,sections:{holdings:{status:'ok'}}}]}} />);
       expect(screen.getAllByText('Trading 212 / holdings: failed')).toHaveLength(1);
       expect(screen.queryByText('Trading 212 / holdings: ok')).not.toBeInTheDocument();
      });
      it('shows missing verification as unknown even when an attempt and complete outcome exist', () => {
       render(<SyncEvidence report={{outcome:'complete',freshness:{Barclays:{holdings:{last_attempt_at:'2026-09-29T18:29:00+00:00',verified_at:null,valuation_at:null,coverage:'unknown',status:'no_op',reason_code:'not_verified',action_code:'none'}}}}} />);
       expect(screen.getByText('Checked: Not reported')).toBeInTheDocument();
       expect(screen.getByText('Valuation: Not reported')).toBeInTheDocument();
       expect(screen.getByText('Coverage: unknown')).toBeInTheDocument();
      });
      it('does not infer refreshed valuations from a legacy successful attempt',()=>{
       render(<SyncEvidence report={{ok:true,steps:[{name:'Broker',status:'ok',detail:null}]}}/>);
       expect(screen.getByText('Refresh outcome: unreported')).toBeInTheDocument();
       expect(screen.getByText(/Successful checks do not prove/)).toBeInTheDocument();
      });
    });

    describe("MobileNav", () => {
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
    });
  });

  describe("SecondaryRoutes", () => {
    describe("Diff", () => {
      const from = { id: 4, as_of_date: "2026-01-01", created_at: "2026-01-02", file_sha256: "a", filename: null, diff_summary: null };
      const to = { ...from, id: 5, as_of_date: "2026-02-01" };
      const attribution: SnapshotAttribution = {
        from_batch: from, to_batch: to, opening_value_gbp: 100, closing_value_gbp: 120,
        raw_value_change_gbp: 20, contributions_gbp: 10, withdrawals_gbp: 0, drip_proxy_gbp: 0,
        net_external_flow_gbp: 10, residual_market_movement_gbp: 10, reconciliation_difference_gbp: 0,
        top_contributors: [], top_detractors: [], notes: ["Estimated, not proven price effects."],
        movements: [{ instrument_id: 7, identifier: "A", security_name: "Alpha", account_name: "ISA", opening_value_gbp: 100,
          closing_value_gbp: 120, raw_value_change_gbp: 20, net_external_flow_gbp: 10, drip_proxy_gbp: 0,
          estimated_market_movement_gbp: 10, contribution_pct_points: null, source_order_ids: [9] }],
        percentage_point_reason: "No validated percentage-point denominator.", unallocated_residual_gbp: 0,
      };
      function show(search: string) {
        render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={[`/activity?tab=changes&${search}`]}>
            <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}><Diff /></PreferencesContext.Provider>
          </MemoryRouter></QueryClientProvider>);
      }
      beforeEach(() => {
        vi.clearAllMocks();
        vi.spyOn(api, "getImports").mockResolvedValue([to, from]);
        vi.spyOn(api, "getSnapshotAttribution").mockResolvedValue(attribution);
        vi.spyOn(api, "compareImports").mockResolvedValue({ from_batch: from, to_batch: to, rows: [] });
      });
      it("opens the exact comparison and selected contribution rather than another default period", async () => {
        show("account=ISA&period=YTD&from=4&to=5&inst=7");
        expect(await screen.findByRole("heading", { name: "Estimated contributions by holding" })).toBeInTheDocument();
        expect(api.getSnapshotAttribution).toHaveBeenCalledWith("ISA", 4, 5);
        await waitFor(() => expect(api.compareImports).toHaveBeenCalledWith(4, 5, "ISA"));
        expect(screen.getByText("Alpha")).toBeInTheDocument();
        expect(screen.getByText("No validated percentage-point denominator.")).toBeInTheDocument();
        expect(screen.getByRole("combobox", { name: "Opening snapshot" })).toHaveValue("4");
      });
      it("rejects malformed identifiers without querying another comparison", () => {
        show("from=4e0&to=5");
        expect(screen.getByRole("alert")).toHaveTextContent("Invalid comparison");
        expect(api.getSnapshotAttribution).not.toHaveBeenCalled();
        expect(api.compareImports).not.toHaveBeenCalled();
      });
    });

    describe("Help", () => {
      describe("Help", () => {
        it("preserves account and period on workspace deep links without leaking the Help tab", () => {
          render(<MemoryRouter initialEntries={["/help?account=ISA&period=1y&tab=old&inst=42"]}><Help /></MemoryRouter>);
          const link = screen.getByRole("link", { name: "Open Portfolio" });
          const url = new URL(link.getAttribute("href")!, "https://local.test");
          expect(url.pathname).toBe("/portfolio");
          expect(url.searchParams.get("account")).toBe("ISA");
          expect(url.searchParams.get("period")).toBe("1y");
          expect(url.searchParams.get("inst")).toBe("42");
          expect(url.searchParams.get("tab")).toBe("performance");
        });
      });
    });

    describe("ImportActivity", () => {
      const imports = [
        {
          id: 22,
          created_at: "2026-07-05T12:00:00Z",
          as_of_date: "2026-07-05",
          filename: "portfolio.xls",
          file_sha256: "hash",
          diff_summary: null,
        },
      ];

      describe("ImportActivity", () => {
        beforeEach(() => {
          vi.spyOn(api, "getImports").mockResolvedValue(imports);
          vi.spyOn(api, "getUnlinkedOrders").mockResolvedValue({ count: 0, orders: [] });
        });

        it("shows immutable import history without upload controls", async () => {
          const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
          render(
            <QueryClientProvider client={client}>
              <MemoryRouter>
                <PreferencesContext.Provider
                  value={{
                    dripThreshold: 1000,
                    setDripThreshold: vi.fn(),
                    accountFilter: "all",
                    setAccountFilter: vi.fn(),
                  }}
                >
                  <ImportActivity />
                </PreferencesContext.Provider>
              </MemoryRouter>
            </QueryClientProvider>,
          );

          expect(await screen.findByText("portfolio.xls")).toBeInTheDocument();
          expect(screen.getByRole("heading", { name: "Import history" })).toBeInTheDocument();
          expect(screen.queryByText("Choose .xls file")).not.toBeInTheDocument();
        });
      });
    });

    describe("TimelineSourceView", () => {
      function show(record: string) {
        render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={[`/activity?tab=source&source=import&record=${record}&account=ISA&period=YTD&inst=7`]}>
            <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
              <TimelineSourceView />
            </PreferencesContext.Provider>
          </MemoryRouter></QueryClientProvider>);
      }
      beforeEach(() => vi.clearAllMocks());
      it("shows the exact read-only source with distinct import and valuation dates", async () => {
        const getSource = vi.spyOn(timelineApi, "getSource").mockResolvedValue({ id: "import:2", kind: "import", date: "2026-01-10",
          occurred_at: "2026-01-10T12:00:00", valuation_date: "2026-01-01", account_names: ["ISA"], instrument_id: null,
          title: "Snapshot file imported", amount_gbp: null, source_type: "import", source_id: 2, source_href: "",
          details: { Filename: "synthetic.csv" }, note: "Administrative event, not a transaction." });
        show("2");
        expect(await screen.findByText("synthetic.csv")).toBeInTheDocument();
        expect(screen.getByText("2026-01-10T12:00:00")).toBeInTheDocument();
        expect(screen.getByText("2026-01-01")).toBeInTheDocument();
        expect(getSource).toHaveBeenCalledWith("import", 2, "ISA");
        expect(screen.getByRole("link", { name: "Back to investigation" })).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&inst=7&tab=holdings&events=on");
      });
      it.each(["2e0", "2&record=3", "2&source=order"])("rejects malformed or ambiguous source IDs: %s", (record) => {
        const request = vi.spyOn(timelineApi, "getSource");
        show(record);
        expect(screen.getByRole("alert")).toHaveTextContent("Invalid source type or record identifier.");
        expect(request).not.toHaveBeenCalled();
      });
    });

    describe("useAnalysisScope", () => {
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
          <WorkspaceTabs label="Views" tabs={location.pathname === "/activity" ? [{key:"orders",label:"Transactions"}] : [{ key: "holdings", label: "Holdings" }, { key: "income", label: "Income" }]} />
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
        it("does not overwrite a local security redirect while materialising scope", async () => {
          function Shell() { useAnalysisScopeUrl(); return <Outlet />; }
          render(<MemoryRouter initialEntries={["/security"]}><Routes><Route element={<Shell />}>
            <Route path="/security" element={<Navigate to="/" replace />} />
            <Route path="/" element={<h1>Overview after local redirect</h1>} />
          </Route></Routes></MemoryRouter>);
          expect(await screen.findByRole("heading", { name: "Overview after local redirect" })).toBeVisible();
        });
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
    });

    describe("useRouteFocus", () => {
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
    });
  });
});

describe("WorkflowComponents", () => {
  describe("HoldingsTable", () => {
    const rows = [{id:1,ticker:'AAA',security_name:'Source Alpha',identifier:'source-id',account_name:'ISA',group_ids:[],latest_value_gbp:100,pnl_gbp:-10,latest_pct_change:null,delta_value_gbp_since_prev_snapshot:null}] as unknown as Instrument[];
    const target = (gap:number, within_tolerance:boolean|null=false, status:AllocationTargets['status']='available') => ({status,groups:[{group_id:2,name:'Core',instrument_ids:[1],actual_value_gbp:100,actual_weight_pct:20,target_weight_pct:30,drift_pp:gap>0?-10:10,gap_gbp:gap,within_tolerance}]} as AllocationTargets);
    it.each([100,-100])('shows backend signed gap %s and drift in a neutral group badge',gap=>{
     render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} targetDrift={target(gap)}/></MemoryRouter>);
     const badge=screen.getByLabelText('Core target drift');
     expect(badge).toHaveTextContent(gap>0?'+£100':'-£100');
     expect(badge).toHaveTextContent(gap>0?'-10.0 pp':'+10.0 pp');
     expect(badge).not.toHaveTextContent(/buy|sell/i);
     expect(badge).toHaveClass('text-slate-400');
    });
    it.each([target(100,true),target(100,null),target(100,false,'unavailable'), {...target(100),groups:[{...target(100).groups[0],gap_gbp:NaN}]}])('suppresses unknown, invalid, or in-band targets',targetDrift=>{
     render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} targetDrift={targetDrift}/></MemoryRouter>);
     expect(screen.queryByLabelText('Core target drift')).not.toBeInTheDocument();
    });
    it('does not manufacture a weight from an invalid valuation denominator',()=>{
     render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} scopeTotalValue={Infinity}/></MemoryRouter>);
     expect(screen.getByText('Weights unavailable: account valuation is not available.')).toBeInTheDocument();
     expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
    });
    beforeEach(()=>{ const store = new Map<string,string>(); vi.stubGlobal('localStorage', {getItem:(k:string)=>store.get(k) ?? null, setItem:(k:string,v:string)=>store.set(k,v),removeItem:(k:string)=>store.delete(k)}); });
    it('shows scoped weight and accessible selection with source search and sort headers',()=>{
     const select=vi.fn();
     render(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={select} scopeTotalValue={1000}/></MemoryRouter>);
     for(const name of ['Security','Account','Value','Weight','Gain / loss','Recent change']) expect(screen.getByRole('button',{name})).toBeInTheDocument();
     expect(screen.getAllByText('10.0%').length).toBeGreaterThanOrEqual(1);
     fireEvent.click(screen.getByRole('button',{name:'View AAA in ISA'})); expect(select).toHaveBeenCalledWith(1);
     fireEvent.change(screen.getByRole('searchbox'),{target:{value:'source-id'}}); expect(screen.getAllByText('10.0%').length).toBeGreaterThanOrEqual(1);
    });
    it('preserves the production search and reset controls without a new filter toolbar',()=>{
     render(<MemoryRouter initialEntries={['/?q=absent&account=ISA&period=1Y&sort=pnl']}><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
     expect(screen.getByRole('button',{name:'Reset view'})).toBeInTheDocument();
     expect(screen.queryByLabelText('Active holdings filters')).not.toBeInTheDocument();
     expect(screen.getByText('No holdings match the active filters.')).toBeInTheDocument();
     fireEvent.change(screen.getByRole('searchbox'),{target:{value:''}});
     expect(screen.getByRole('columnheader',{name:'Gain / loss'})).toHaveAttribute('aria-sort','descending');
    });
    it('distinguishes an empty account from unavailable weights',()=>{
     const view=render(<MemoryRouter><HoldingsTable instruments={[]} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
     expect(screen.getByText('No holdings in this account scope.')).toBeInTheDocument();
     view.rerender(<MemoryRouter><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
     expect(screen.getByText('Weights unavailable: account valuation is not available.')).toBeInTheDocument();
    });
    it('uses URL sorting over saved preferences and resets optional columns',()=>{
     localStorage.setItem('holdings-view-v1',JSON.stringify({version:1,sort:'pnl',direction:'asc',classification:true}));
     render(<MemoryRouter initialEntries={['/?sort=value&direction=desc']}><HoldingsTable instruments={rows} groups={[]} selectedId={null} onSelect={()=>{}} /></MemoryRouter>);
     expect(screen.getByRole('columnheader',{name:'Value'})).toHaveAttribute('aria-sort','descending');
     expect(screen.getByRole('checkbox',{name:'Classification columns'})).toBeChecked();
     fireEvent.click(screen.getByRole('button',{name:'Reset view'}));
     expect(screen.getByRole('checkbox',{name:'Classification columns'})).not.toBeChecked();
    });
  });

  describe("ImportPanel", () => {
    function show() {
      return render(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <PreferencesContext.Provider
            value={{
              dripThreshold: 1000,
              setDripThreshold: vi.fn(),
              accountFilter: "all",
              setAccountFilter: vi.fn(),
            }}
          >
            <ImportPanel />
          </PreferencesContext.Provider>
        </QueryClientProvider>,
      );
    }

    describe("ImportPanel Trading 212 sync", () => {
      beforeEach(() => {
        vi.restoreAllMocks();
        vi.spyOn(api, "syncAll").mockImplementation(() => Promise.reject(new Error("unexpected combined sync")));
        vi.spyOn(api, "requestSync").mockImplementation(() => Promise.reject(new Error("unexpected service sync")));
        vi.spyOn(api, "getSyncStatus").mockResolvedValue({ manual_sync_enabled: true, service_trigger_enabled: false, accounts: [], stale_after_days: 7, last_run: null, running: false });
        vi.spyOn(api, "getTrading212Status").mockResolvedValue({
          configured: true,
          account_name: "Trading 212",
        });
        vi.spyOn(api, "syncTrading212Portfolio").mockResolvedValue({
          batch: {
            id: 1,
            created_at: "2026-09-07T12:00:00Z",
            as_of_date: "2026-09-07",
            file_sha256: "hash",
            filename: "trading212-api-portfolio.json",
            diff_summary: null,
          },
          summary: { row_count: 2 },
        });
        vi.spyOn(api, "syncTrading212Orders").mockResolvedValue({
          id: 1,
          created_at: "2026-09-07T12:00:00Z",
          filename: "trading212-api-orders.json",
          row_count: 1,
        });
      });

      it("syncs external cash flows separately and refreshes Dashboard data", async () => {
        const sync = vi.spyOn(api, "syncTrading212").mockResolvedValue({
          account_name: "Trading 212", snapshot: "imported", snapshot_rows: 2,
          orders: "imported", order_rows: 1, cash_flows_imported: 4, cash_flows_total: 4,
          fetched_at: "2026-09-09T12:00:00Z",
        });
        const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
        show();
        const button = await screen.findByRole("button", { name: "Sync Trading 212" });
        await waitFor(() => expect(button).toBeEnabled());
        fireEvent.click(button);
        await waitFor(() => expect(sync).toHaveBeenCalledOnce());
        expect(await screen.findByText(/cash: 4 new \/ 4 total/)).toBeInTheDocument();
        expect(sync).toHaveBeenCalledWith(false);
        expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Import Barclays XLS snapshot" })).toBeInTheDocument();
        expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
        expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
        expect(invalidate).toHaveBeenCalled();
      });

      it("offers a direct Trading 212 refresh with legacy sync controls disabled", async () => {
        vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: false, accounts: [], stale_after_days: 7, last_run: null, running: false });
        const sync = vi.spyOn(api, "syncTrading212").mockResolvedValue({
          account_name: "Trading 212", snapshot: "unchanged", snapshot_rows: null,
          orders: "unchanged", order_rows: null, cash_flows_imported: 0, cash_flows_total: 4,
          fetched_at: "2026-09-09T12:00:00Z",
        });
        show();
        const button = await screen.findByRole("button", { name: "Sync Trading 212" });
        await waitFor(() => expect(button).toBeEnabled());
        fireEvent.click(button);
        await waitFor(() => expect(sync).toHaveBeenCalledWith(false));
        expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
        expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
        expect(screen.queryByRole("button", { name: "Sync all accounts" })).not.toBeInTheDocument();
      });

      it("requests the isolated worker without web broker credentials and polls to completion", async () => {
        vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
        vi.mocked(api.getTrading212Status).mockResolvedValue({ configured: false, account_name: "Trading 212" });
        const direct = vi.spyOn(api, "syncTrading212");
        const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
          expect(String(url)).toBe("/api/sync/trading212/request");
          return new Response(JSON.stringify(options?.method === "POST"
            ? { state: "accepted", request_id: "synthetic-request" }
            : { state: "completed", request_id: "synthetic-request", last_run: null }), { status: 200 });
        });
        const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
        show();
        const button = await screen.findByRole("button", { name: "Sync Trading 212" });
        await waitFor(() => expect(button).toBeEnabled());
        expect(screen.queryByText(/credentials to .env/)).not.toBeInTheDocument();
        fireEvent.click(button);
        await waitFor(() => expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1));
        await waitFor(() => expect(fetch.mock.calls.some(([, options]) => options?.method !== "POST")).toBe(true));
        expect(fetch.mock.calls[0][1]?.method).toBe("POST");
        expect(fetch.mock.calls[0][1]?.body).toBeUndefined();
        await waitFor(() => expect(button).toBeEnabled());
        expect(direct).not.toHaveBeenCalled();
        expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
        expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
        expect(invalidate).toHaveBeenCalled();
        expect(screen.getByRole("button", { name: "Import Barclays XLS snapshot" })).toBeInTheDocument();
      });

      it.each([
        { providerStatus: "committed_with_attention", holdings: "needs_attention", message: "Verified history was retained. The portfolio valuation was not updated." },
        { providerStatus: "ok", holdings: "imported", message: "Some work completed. Check the section results and service logs." },
      ])("reports the actual valuation section on a partial run: $holdings", async ({ providerStatus, holdings, message }) => {
        vi.mocked(api.getSyncStatus).mockResolvedValue({ manual_sync_enabled: false, service_trigger_enabled: true, accounts: [], stale_after_days: 7, last_run: null, running: false });
        const sections = { holdings: { status: holdings }, cash: { status: holdings }, orders: { status: "imported" } };
        const steps = [{ name: "Trading 212", status: providerStatus, sections },
          ...(providerStatus === "ok" ? [{ name: "Sync step", status: "failed", sections: {} }] : [])];
        vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => new Response(JSON.stringify(options?.method === "POST"
          ? { state: "accepted", request_id: "partial-request" }
          : { state: "failed", request_id: "partial-request", last_run: { outcome: "partial", finished_at: "2026-01-01T12:02:00Z", steps } })));
        show();
        const button = await screen.findByRole("button", { name: "Sync Trading 212" });
        await waitFor(() => expect(button).toBeEnabled());
        fireEvent.click(button);
        expect(await screen.findByRole("alert")).toHaveTextContent(message);
        expect(screen.getByText(`Trading 212 / holdings: ${holdings}`)).toBeInTheDocument();
        expect(screen.getByText("Refresh outcome: partial")).toBeInTheDocument();
      });

      it("keeps the Barclays XLS import as a manual upload", async () => {
        const file = new File(["portfolio"], "portfolio.xls");
        const importXls = vi.spyOn(api, "importXls").mockResolvedValue({
          batch: {
            id: 2,
            created_at: "2026-09-10T12:00:00Z",
            as_of_date: "2026-09-10",
            file_sha256: "barclays-hash",
            filename: "portfolio.xls",
            diff_summary: null,
          },
          summary: {},
        });
        const { container } = show();
        const fileInput = container.querySelector<HTMLInputElement>('input[type="file"][accept=".xls"]');
        expect(fileInput).not.toBeNull();
        fireEvent.change(fileInput!, { target: { files: [file] } });
        const dateInput = container.querySelector<HTMLInputElement>('input[type="date"]');
        expect(dateInput).not.toBeNull();
        fireEvent.change(dateInput!, { target: { value: "2026-09-10" } });
        fireEvent.click(screen.getByRole("button", { name: "Import Barclays XLS snapshot" }));
        await waitFor(() => expect(importXls).toHaveBeenCalledWith(file, "2026-09-10", false));
        expect(await screen.findByText("Import complete.")).toBeInTheDocument();
        expect(vi.mocked(api.syncAll)).not.toHaveBeenCalled();
        expect(vi.mocked(api.requestSync)).not.toHaveBeenCalled();
      });

      it("keeps the Trading 212 refresh disabled when credentials are not configured", async () => {
        vi.mocked(api.getTrading212Status).mockResolvedValue({ configured: false, account_name: "Trading 212" });
        show();
        expect(await screen.findByRole("button", { name: "Sync Trading 212" })).toBeDisabled();
        expect(await screen.findByText(/credentials to .env/)).toBeInTheDocument();
      });

    });
  });

  describe("ClassificationQueue", () => {
    const incompleteInstrument = {
      id: 7,
      account_name: "ISA",
      identifier: "EQQQ",
      security_name: "NASDAQ ETF",
      is_cash: false,
      ticker: null,
      sector: null,
      region: null,
      asset_class: null,
      closed_at: null,
    } as Instrument;

    const classifiedInstrument = {
      id: 8,
      account_name: "ISA",
      identifier: "AAPL",
      security_name: "Apple Inc.",
      is_cash: false,
      ticker: "AAPL",
      sector: "Technology",
      region: "US",
      asset_class: "Equity",
      closed_at: null,
    } as Instrument;

    function renderQueue() {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(
        <QueryClientProvider client={client}>
          <ClassificationQueue />
        </QueryClientProvider>,
      );
    }

    describe("ClassificationQueue", () => {
      beforeEach(() => {
        vi.clearAllMocks();
        vi.spyOn(api, "getInstruments").mockResolvedValue([incompleteInstrument]);
        vi.spyOn(api, "updateInstrumentMarket").mockResolvedValue({
          ...incompleteInstrument,
          ticker: "EQQQ.L",
          asset_class: "Equity ETF",
        });
      });

      it("surfaces incomplete open instruments and saves reviewed metadata", async () => {
        renderQueue();

        expect(screen.getByRole("heading", { name: "Classification queue" })).toBeInTheDocument();
        const tickerInput = await screen.findByLabelText("Ticker for EQQQ");
        fireEvent.change(tickerInput, {
          target: { value: "EQQQ.L" },
        });
        fireEvent.change(screen.getByLabelText("Asset class for EQQQ"), {
          target: { value: "Equity ETF" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save EQQQ" }));

        await waitFor(() =>
          expect(api.updateInstrumentMarket).toHaveBeenCalledWith(7, {
            ticker: "EQQQ.L",
            asset_class: "Equity ETF",
            sector: null,
            region: null,
          }),
        );
      });

      it("keeps failed rows highlighted and retryable, then reports a successful retry", async () => {
        vi.mocked(api.getInstruments).mockResolvedValue([classifiedInstrument]);
        vi.mocked(api.updateInstrumentMarket)
          .mockRejectedValueOnce(new Error("temporary failure"))
          .mockResolvedValueOnce({ ...classifiedInstrument, region: "USA" });
        renderQueue();

        fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
        fireEvent.change(await screen.findByLabelText("Region for AAPL"), { target: { value: "USA" } });
        fireEvent.click(screen.getByRole("button", { name: "Save changes (1)" }));

        expect(await screen.findByRole("alert")).toHaveTextContent("0 saved; 1 could not be saved");
        expect(screen.getByRole("row", { name: /AAPL/ })).toHaveTextContent("Changed");
        expect(screen.getByLabelText("Region for AAPL")).toHaveClass("border-amber-300/80");
        fireEvent.click(screen.getByRole("button", { name: "Save changes (1)" }));
        await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 classification saved."));
        expect(api.updateInstrumentMarket).toHaveBeenCalledTimes(2);
      });

      it("keeps a non-standard Class value available to restore before saving", async () => {
        const customClassHolding = { ...classifiedInstrument, asset_class: "Investment Trust" } as Instrument;
        vi.mocked(api.getInstruments).mockResolvedValue([customClassHolding]);
        renderQueue();

        fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
        const classSelect = await screen.findByLabelText("Class for AAPL");
        fireEvent.change(classSelect, { target: { value: "Equity" } });
        expect(within(classSelect).getByRole("option", { name: "Investment Trust" })).toBeInTheDocument();
        fireEvent.change(classSelect, { target: { value: "Investment Trust" } });
        expect(screen.getByRole("button", { name: "Save changes (0)" })).toBeDisabled();
      });

      it("requires every classification cell before enabling bulk save", async () => {
        vi.mocked(api.getInstruments).mockResolvedValue([classifiedInstrument]);
        renderQueue();

        fireEvent.click(await screen.findByRole("button", { name: "Show classification editor" }));
        const classSelect = await screen.findByLabelText("Class for AAPL");
        expect(within(classSelect).queryByRole("option", { name: "Choose…" })).not.toBeInTheDocument();
        fireEvent.change(screen.getByLabelText("Sector for AAPL"), { target: { value: "  " } });

        expect(screen.getByRole("button", { name: "Save changes (1)" })).toBeDisabled();
        expect(screen.getByRole("alert")).toHaveTextContent("Class, Sector, and Region are required");
        expect(api.updateInstrumentMarket).not.toHaveBeenCalled();

        fireEvent.change(screen.getByLabelText("Sector for AAPL"), { target: { value: "Technology" } });
        expect(screen.getByRole("button", { name: "Save changes (0)" })).toBeDisabled();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      });

      it("keeps the unmatched queue first and supports sorting and bulk-editing classifications", async () => {
        const secondHolding = {
          ...classifiedInstrument,
          id: 9,
          identifier: "MSFT",
          security_name: "Microsoft Corp.",
          sector: "Diverse",
          region: "USA",
        } as Instrument;
        vi.mocked(api.getInstruments).mockResolvedValue([incompleteInstrument, classifiedInstrument, secondHolding]);
        renderQueue();

        const queueHeading = await screen.findByRole("heading", { name: "Classification queue" });
        await screen.findByLabelText("Ticker for EQQQ");
        const editorHeading = screen.getByRole("heading", { name: "Edit existing classifications" });
        expect(queueHeading.compareDocumentPosition(editorHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        const toggle = screen.getByRole("button", { name: "Show classification editor" });
        expect(toggle.querySelector("svg.lucide-chevron-down")).toBeInTheDocument();
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        expect(screen.queryByRole("table", { name: "Existing classifications" })).not.toBeInTheDocument();
        fireEvent.click(toggle);

        const table = await screen.findByRole("table", { name: "Existing classifications" });
        for (const label of ["Holding", "Account", "Class", "Sector", "Region", "Status"]) {
          const button = within(table).getByRole("button", { name: new RegExp(`Sort by ${label}`) });
          fireEvent.click(button);
          expect(button.closest("th")?.getAttribute("aria-sort")).toMatch(/ascending|descending/);
        }
        const regionSort = within(table).getByRole("button", { name: /Sort by Region/ });

        fireEvent.click(regionSort);
        expect(within(table).getAllByRole("row")[1]).toHaveTextContent("AAPL");
        fireEvent.click(regionSort);
        expect(within(table).getAllByRole("row")[1]).toHaveTextContent("MSFT");

        fireEvent.change(screen.getByLabelText("Class for AAPL"), { target: { value: "Bond" } });
        fireEvent.change(screen.getByLabelText("Region for MSFT"), { target: { value: "United States" } });
        expect(within(table).getByRole("row", { name: /AAPL/ })).toHaveTextContent("Changed");
        expect(within(table).getByRole("row", { name: /MSFT/ })).toHaveTextContent("Changed");
        const aaplClass = screen.getByLabelText("Class for AAPL");
        const aaplSector = screen.getByLabelText("Sector for AAPL");
        expect(aaplClass).toHaveClass("border-amber-300/80");
        expect(aaplClass.closest("td")).toHaveClass("bg-amber-400/[0.09]");
        expect(aaplSector).not.toHaveClass("border-amber-300/80");
        expect(aaplSector.closest("td")).not.toHaveClass("bg-amber-400/[0.09]");
        expect(within(table).getByRole("row", { name: /AAPL/ })).not.toHaveClass("bg-amber-400/[0.04]");

        const saveButton = screen.getByRole("button", { name: "Save changes (2)" });
        expect(saveButton).toBeEnabled();
        expect(api.updateInstrumentMarket).not.toHaveBeenCalled();
        fireEvent.click(saveButton);

        await waitFor(() => {
          expect(api.updateInstrumentMarket).toHaveBeenCalledTimes(2);
          expect(api.updateInstrumentMarket).toHaveBeenCalledWith(8, { asset_class: "Bond" });
          expect(api.updateInstrumentMarket).toHaveBeenCalledWith(9, { region: "United States" });
        });
      });

    });
  });

  describe("investigationIntegration", () => {
    it('links a contributor to the selected holding with comparison and period intact',()=>{
     const attribution={notes:[],movements:[{instrument_id:1,security_name:'Alpha',identifier:'A',account_name:'ISA'}]} as unknown as SnapshotAttribution;
     render(<MemoryRouter initialEntries={['/activity?tab=changes&from=2&to=5&period=1Y']}><ContributionDetails attribution={attribution} instrumentId={1}/></MemoryRouter>);
     const href=screen.getByRole('link',{name:'Explore Alpha holding'}).getAttribute('href')!;
     const p=new URL(href,'http://test').searchParams;expect(p.get('inst')).toBe('1');expect(p.get('from')).toBe('2');expect(p.get('to')).toBe('5');expect(p.get('period')).toBe('1Y');
    });
    it('links group results to a real membership filter',()=>{
     const group={group_id:3,name:'Core',member_count:1,total_current_value_gbp:100,total_net_cost_gbp:100,total_pnl_gbp:0,timeseries:[],members:[]} as unknown as GroupPerformance;
     render(<MemoryRouter initialEntries={['/portfolio?account=ISA&period=6M']}><GroupPerformancePanel groups={[group]} isLoading={false}/></MemoryRouter>);
     const href=screen.getByRole('link',{name:'Explore Core holdings'}).getAttribute('href')!;
     expect(href).toContain('group=3');expect(href).toContain('account=ISA');expect(href).toContain('period=6M');
    });
  });
});

describe("IncomeAnalysisPanel", () => {
  beforeEach(()=>{vi.spyOn(api,"getOrders").mockResolvedValue([]);vi.spyOn(api,"getOrderPositions").mockResolvedValue([]);});
  afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
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
});

describe("TargetDriftPanel", () => {
  beforeEach(()=>{vi.spyOn(api,"getInstruments").mockResolvedValue([]);vi.spyOn(api,"getGroups").mockResolvedValue([]);});
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("explains unavailable target sets and links to their existing editor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>({status:"unavailable",account_name:null,invested_value_gbp:100,excluded_cash_gbp:25,tolerance_pp:2,reasons:["Set a target for every group"],groups:[],cash_policy:"Cash excluded"})}));
    render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter><Groups /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole("heading", {name:"Target drift"})).toBeInTheDocument();
    expect(await screen.findByText("Set a target for every group")).toBeInTheDocument();
    expect(screen.getByRole("link", {name:"Resolve target configuration"})).toHaveAttribute("href", expect.stringContaining("/portfolio?tab=groups"));
  });
});

describe("allocationIntegration", () => {
  beforeEach(()=>{let value:string|null=null;vi.stubGlobal('localStorage',{getItem:()=>value,setItem:(_k:string,v:string)=>{value=v;}});});
  beforeEach(()=>{vi.spyOn(api,'getInstruments').mockResolvedValue([]);vi.spyOn(api,'getGroups').mockResolvedValue([]);vi.spyOn(api,'createGroup').mockResolvedValue({id:3,name:'New tag',target_allocation_pct:null} as never);});
  const before={status:'available',account_name:null,invested_value_gbp:100,excluded_cash_gbp:25,tolerance_pp:2,target_sum_tolerance_pp:0.01,cash_policy:'Cash excluded',reasons:[],groups:[{group_id:1,name:'Core',actual_value_gbp:100,actual_weight_pct:100,target_weight_pct:100,drift_pp:0,gap_gbp:0,within_tolerance:true,instrument_ids:[1]}]};
  const response=(data:unknown)=>({ok:true,json:async()=>data});
  afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
  function setup(children:React.ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>);return client;}
  async function submit(){fireEvent.change(await screen.findByLabelText('Contribution (GBP)'),{target:{value:'50'}});fireEvent.change(screen.getByLabelText('Core allocation (GBP)'),{target:{value:'50'}});fireEvent.click(screen.getByRole('button',{name:'Calculate scenario'}));}
  it('tolerance edits update sibling prerequisites and clear results',async()=>{
   const requests:string[]=[];
   vi.stubGlobal('fetch',vi.fn(async(url:string)=>{requests.push(String(url));if(String(url).includes('allocation-scenario'))return response({before,after:{...before,invested_value_gbp:150},assumption:'Hypothetical contribution; no orders created.'});const tolerance=Number(new URL(String(url),'http://test').searchParams.get('tolerance_pp'));return response({...before,tolerance_pp:tolerance});}));
   setup(<><TargetDriftPanel/><AllocationScenarioPanel/></>);
   await submit();await screen.findByRole('table',{name:'Before and hypothetical after'});
   fireEvent.change(screen.getByLabelText('Target drift tolerance'),{target:{value:'12'}});
   await waitFor(()=>expect(requests.some(x=>x.includes('allocation-targets')&&x.includes('tolerance_pp=12'))).toBe(true));
   await waitFor(()=>expect(screen.queryByRole('table',{name:'Before and hypothetical after'})).not.toBeInTheDocument());
   fireEvent.change(screen.getByLabelText('Contribution (GBP)'),{target:{value:'60'}});
   fireEvent.change(screen.getByLabelText('Core allocation (GBP)'),{target:{value:'60'}});
   fireEvent.click(screen.getByRole('button',{name:'Calculate scenario'}));
   await waitFor(()=>expect(requests.filter(x=>x.includes('allocation-scenario'))).toHaveLength(2));
   expect(new URL(requests.filter(x=>x.includes('allocation-scenario'))[1],'http://test').searchParams.get('tolerance_pp')).toBe('12');
  });
  it('adding a group refreshes target prerequisites',async()=>{
   const fetcher=vi.fn(async()=>response(before));vi.stubGlobal('fetch',fetcher);
   setup(<Groups/>);await screen.findByRole('region',{name:'Target comparison'});
   const calls=fetcher.mock.calls.length;
   fireEvent.change(screen.getByPlaceholderText('Group name (e.g. Tech, ETFs, EM)'),{target:{value:'New tag'}});
   fireEvent.click(screen.getByRole('button',{name:'Add group'}));
   await waitFor(()=>expect(api.createGroup).toHaveBeenCalled());
   await waitFor(()=>expect(screen.getByPlaceholderText('Group name (e.g. Tech, ETFs, EM)')).toHaveValue(''));
   await waitFor(()=>expect(fetcher.mock.calls.length).toBeGreaterThan(calls));
   expect(screen.getByRole('region',{name:'Target comparison'})).toBeInTheDocument();
  });
  it('recalculation after baseline change never exposes previous cached scenario',async()=>{
   let scenarios=0;
   vi.stubGlobal('fetch',vi.fn(async(url:string)=>{if(!String(url).includes('allocation-scenario'))return response(before);scenarios++;if(scenarios===2)return new Promise(()=>{});return response({before,after:{...before,invested_value_gbp:150},assumption:'OLD BASELINE RESULT'});}));
   const client=setup(<AllocationScenarioPanel/>);await submit();await screen.findByText('OLD BASELINE RESULT');
   client.setQueryData(['allocation-targets',null,2],{...before,invested_value_gbp:200,groups:[{...before.groups[0],actual_value_gbp:200}]});
   await waitFor(()=>expect(screen.queryByText('OLD BASELINE RESULT')).not.toBeInTheDocument());
   await submit();await waitFor(()=>expect(scenarios).toBe(2));
   expect(screen.queryByText('OLD BASELINE RESULT')).not.toBeInTheDocument();
  });
});
