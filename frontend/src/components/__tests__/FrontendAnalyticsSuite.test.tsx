import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AllocationCategory, type DrawdownEpisode, type Instrument, type PerformanceSummary, type SnapshotAttribution, type SyncRun } from "../../lib/api";
import { AllocationDonut } from "../AllocationDonut";
import { AttributionSummaryCard } from "../AttributionSummaryCard";
import { AttributionWaterfall } from "../AttributionWaterfall";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataConfidencePanel } from "../DataConfidencePanel";
import publicReport from "./fixtures/public-sync-v2.json";
import { dataQualityApi, type DataConfidence } from "../../lib/dataQualityApi";
import { PreferencesContext } from "../../state/usePreferences";
import { MemoryRouter } from "react-router-dom";
import { DrawdownEpisodes } from "../DrawdownEpisodes";
import { type ReactNode } from "react";
import { GroupsSection } from "../GroupsSection";
import { OrderHistorySection } from "../OrderHistorySection";
import { type OrderPage } from "../../lib/orderPageApi";
import { timelineApi, type TimelineEvent, type TimelineResponse } from "../../lib/timelineApi";
import { TimelineEvents } from "../TimelineEvents";
import { TimelineMarkerLabel } from "../TimelineMarkerLabel";
import { AnalysisScopeContext } from "../../state/useAnalysisScope";
import { PerformancePanel } from "../PerformancePanel";

describe("AnalyticsComponents", () => {
  describe("AllocationDonut", () => {
    const categories: AllocationCategory[] = [
      { label: "Equity ETF", value: 5400, weightPct: 54, count: 4 },
      { label: "Bond ETF", value: 2700, weightPct: 27, count: 2 },
      { label: "Property", value: 900, weightPct: 9, count: 1 },
      { label: "Unclassified", value: 1000, weightPct: 10, count: 1 },
    ];

    describe("AllocationDonut", () => {
      it("uses invested value in the centre instead of repeating a technical HHI headline", () => {
        render(<AllocationDonut categories={categories} totalValue={10000} />);
        expect(screen.getByTestId("allocation-donut-center")).toHaveTextContent("£10k");
        expect(screen.getByText("Invested")).toBeInTheDocument();
        expect(screen.queryByText("HHI")).not.toBeInTheDocument();
      });
      it("keeps every category explicit in an accessible table with meaningful headings", () => {
        render(<AllocationDonut categories={categories} totalValue={10000} dimension="sector" />);
        const table = screen.getByRole("table", { name: "By sector" });
        expect(within(table).getByRole("columnheader", { name: "Sector" })).toBeInTheDocument();
        for (const category of categories) {
          const row = within(table).getByRole("rowheader", { name: category.label }).closest("tr")!;
          expect(within(row).getByText(`${category.weightPct.toFixed(1)}%`)).toBeInTheDocument();
          expect(within(row).getByText(String(category.count))).toBeInTheDocument();
        }
      });
      it("makes exact values reachable by a button rather than hover alone", () => {
        render(<AllocationDonut categories={categories} totalValue={10000} dimension="currency" />);
        expect(screen.getByRole("columnheader", { name: "Source currency" })).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Show exact values" }));
        expect(screen.getByText("£5,400.00")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Show rounded values" })).toHaveAttribute("aria-pressed", "true");
      });
      it("handles empty allocation without a donut", () => {
        render(<AllocationDonut categories={[]} totalValue={0} />);
        expect(screen.getByText("No positions")).toBeInTheDocument();
      });
    });
  });

  describe("AttributionSummaryCard", () => {
    const attribution: SnapshotAttribution = {
      from_batch: {
        id: 4,
        created_at: "2025-01-01T10:00:00Z",
        as_of_date: "2025-01-01",
        file_sha256: "from",
        filename: "from.csv",
        diff_summary: null,
      },
      to_batch: {
        id: 5,
        created_at: "2025-02-01T10:00:00Z",
        as_of_date: "2025-02-01",
        file_sha256: "to",
        filename: "to.csv",
        diff_summary: null,
      },
      opening_value_gbp: 1000,
      closing_value_gbp: 1300,
      raw_value_change_gbp: 300,
      contributions_gbp: 100,
      withdrawals_gbp: 50,
      drip_proxy_gbp: 20,
      net_external_flow_gbp: 50,
      residual_market_movement_gbp: 230,
      reconciliation_difference_gbp: 0,
      top_contributors: [
        {
          instrument_id: 1,
          identifier: "AAA",
          security_name: "Alpha fund",
          account_name: "ISA",
          opening_value_gbp: 600,
          closing_value_gbp: 850,
          raw_value_change_gbp: 250,
          net_external_flow_gbp: 100,
          drip_proxy_gbp: 20,
          estimated_market_movement_gbp: 130,
        },
      ],
      top_detractors: [
        {
          instrument_id: 2,
          identifier: "BBB",
          security_name: "Beta fund",
          account_name: "ISA",
          opening_value_gbp: 500,
          closing_value_gbp: 450,
          raw_value_change_gbp: -50,
          net_external_flow_gbp: 0,
          drip_proxy_gbp: 0,
          estimated_market_movement_gbp: -50,
        },
      ],
      notes: ["Residual market movement is an attribution estimate."],
    };

    describe("AttributionSummaryCard", () => {
      it("summarises boundaries, flows, DRIP, market movement and movers", () => {
        render(<AttributionSummaryCard attribution={attribution} />);

        expect(screen.getByText("What changed")).toBeInTheDocument();
        expect(screen.getByRole("row", { name: "Opening value £1,000" })).toBeInTheDocument();
        expect(screen.getByRole("row", { name: "Closing value £1,300" })).toBeInTheDocument();
        expect(screen.getAllByRole("table")).toHaveLength(1);
        expect(screen.getByRole("table")).toBeVisible();
        expect(screen.getByText("DRIP proxy")).toBeInTheDocument();
        expect(screen.getByText("+£20")).toBeInTheDocument();
        expect(screen.getByText("Estimated market movement")).toBeInTheDocument();
        expect(screen.getByText("+£230")).toBeInTheDocument();
        expect(screen.getByText("Alpha fund")).toBeInTheDocument();
        expect(screen.getByText("Beta fund")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /full snapshot changes/i })).toHaveAttribute(
          "href",
          "/activity?tab=changes&from=4&to=5",
        );
        expect(screen.queryByText("Value walk")).not.toBeInTheDocument();
        expect(screen.getByText("Residual market movement is an attribution estimate.")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Alpha fund/ })).toHaveAttribute("href", "/activity?tab=changes&from=4&to=5&account=ISA&inst=1");
        expect(
          screen.getByText("Exact reconciliation before display rounding."),
        ).toBeInTheDocument();
      });

      it("surfaces a non-zero reconciliation difference in the waterfall", () => {
        render(
          <AttributionSummaryCard
            attribution={{ ...attribution, reconciliation_difference_gbp: 5 }}
          />,
        );
        expect(screen.getByText("Reconciliation difference")).toBeInTheDocument();
        expect(screen.getByText(/Unreconciled difference £5/)).toBeInTheDocument();
      });

      it("keeps the dashboard breakdown, movers and material warnings without routine prose", () => {
        render(<AttributionSummaryCard compact attribution={{ ...attribution, unallocated_residual_gbp: 15, notes: [
          ...attribution.notes,
          "2 flow order(s) were not linked to an instrument; per-instrument estimates do not allocate those flows.",
          "Some account valuations are carried forward at these boundaries; market movement is not synchronously observed.",
        ] }} />);
        expect(screen.getByRole("row", { name: "Closing value £1,300" })).toBeVisible();
        expect(screen.getByRole("link", { name: /Alpha fund/ })).toBeVisible();
        expect(screen.getByRole("link", { name: /full snapshot changes/i })).toBeVisible();
        expect(screen.getByText("Unallocated residual adjustment: +£15.")).toBeVisible();
        expect(screen.getByText("Some account values were carried forward.")).toBeVisible();
        expect(screen.getByText("2 unlinked orders are not allocated to holdings.")).toBeVisible();
        expect(screen.queryByText("Residual market movement is an attribution estimate.")).not.toBeInTheDocument();
        expect(screen.queryByText("Exact reconciliation before display rounding.")).not.toBeInTheDocument();
      });

      it.each([false, true])("shows the actual reason when attribution is unavailable (compact=%s)", (compact) => {
        render(
          <AttributionSummaryCard
            compact={compact}
            attribution={{
              ...attribution,
              from_batch: null,
              opening_value_gbp: null,
              closing_value_gbp: null,
              raw_value_change_gbp: null,
              contributions_gbp: null,
              withdrawals_gbp: null,
              drip_proxy_gbp: null,
              net_external_flow_gbp: null,
              residual_market_movement_gbp: null,
              reconciliation_difference_gbp: null,
              top_contributors: [],
              top_detractors: [],
              notes: [...attribution.notes, "No previous snapshot is available for this selection."],
            }}
          />,
        );

        expect(screen.getByText("Attribution unavailable")).toBeInTheDocument();
        expect(screen.getByText(/No previous snapshot/)).toBeVisible();
        if (compact) expect(screen.queryByText(attribution.notes[0])).not.toBeInTheDocument();
      });
    });
  });

  describe("AttributionWaterfall", () => {
    const attribution: SnapshotAttribution = {
      from_batch: null, to_batch: null, opening_value_gbp: 1000, closing_value_gbp: 1300,
      raw_value_change_gbp: 300, contributions_gbp: 100, withdrawals_gbp: 50, drip_proxy_gbp: 20,
      net_external_flow_gbp: 50, residual_market_movement_gbp: 230, reconciliation_difference_gbp: 0,
      top_contributors: [], top_detractors: [], notes: [],
    };

    describe("compact attribution breakdown", () => {
      it("signs movements without implying the residual is a proven price effect", () => {
        render(<AttributionWaterfall attribution={attribution} />);
        expect(screen.getByRole("row", { name: "Contributions +£100" })).toBeInTheDocument();
        expect(screen.getByRole("row", { name: "Withdrawals −£50" })).toBeInTheDocument();
        expect(screen.getByRole("row", { name: "DRIP proxy +£20" })).toBeInTheDocument();
        expect(screen.getByRole("row", { name: "Estimated market movement +£230" })).toBeInTheDocument();
      });
      it("does not turn missing components or reconciliation into zero", () => {
        render(<AttributionWaterfall attribution={{ ...attribution, contributions_gbp: null, reconciliation_difference_gbp: null }} />);
        expect(screen.getByRole("row", { name: "Contributions Unavailable" })).toBeInTheDocument();
        expect(screen.getByText("Reconciliation unavailable.")).toBeInTheDocument();
      });
    });
  });

  describe("DataConfidencePanel", () => {
    const data: DataConfidence = {
      scope: { account_name: "ISA", requested_start: null, requested_end: null, effective_start: "2026-01-01", effective_end: "2026-02-01", valuation_dates: [], warnings: [] },
      evaluated_on: "2026-02-05", stale_after_days: 14, snapshots: [],
      transactions: { count: 7, first_date: "2026-01-01", last_date: "2026-02-01", unmatched_count: 0, review_count: 0, completeness: "unknown" },
      classification: {}, market_history: { covered_value_gbp: 0, non_cash_value_gbp: 100, covered_pct: 0,
        aligned_observations: 0, cache_gate_met: false, validation_pending: true, reasons: ["Provider validation pending."] },
      metric_reasons: [], attention: [],
    };
    function show() {
      render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
          <DataConfidencePanel />
        </PreferencesContext.Provider>
      </QueryClientProvider>);
    }
    beforeEach(() => {
      vi.spyOn(api,"getSyncStatus").mockResolvedValue({manual_sync_enabled:false,accounts:[],stale_after_days:7,running:false,last_run:null,outcome:"no_op",freshness:{}});
      const values = new Map<string, string>();
      vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value) });
    });
    afterEach(() => vi.unstubAllGlobals());

    it("discloses unknown transaction completeness and keeps unavailable proxy history separate from core checks", async () => {
      const request = vi.spyOn(dataQualityApi, "getConfidence").mockResolvedValue(data);
      show();
      expect(await screen.findByText("Core data checks healthy — view coverage and limitations")).toBeInTheDocument();
      expect(screen.getByText(/Completeness is unknown/)).toBeInTheDocument();
      expect(await screen.findByText("Refresh outcome: no_op")).toBeInTheDocument();
      expect(screen.getByText(/does not block snapshot or holdings analysis/)).toBeInTheDocument();
      expect(request).toHaveBeenCalledWith("ISA", "ALL", 14);
      fireEvent.change(screen.getByRole("combobox", { name: "Snapshot freshness tolerance" }), { target: { value: "30" } });
      await waitFor(() => expect(request).toHaveBeenCalledWith("ISA", "ALL", 30));
    });

    it('shows real serialized last-run v2 evidence on the full confidence surface', async () => {
      vi.mocked(api.getSyncStatus).mockResolvedValue({manual_sync_enabled:false,accounts:[],stale_after_days:7,running:false,last_run:publicReport as SyncRun});
      vi.spyOn(dataQualityApi, 'getConfidence').mockResolvedValue(data);
      show();
      expect(await screen.findByText('Trading 212 / holdings: failed')).toBeInTheDocument();
      expect(screen.getByText('Checked: 2026-09-01T18:30:00+00:00')).toBeInTheDocument();
      expect(screen.getByText('Attempt: 2026-09-29T18:29:00+00:00')).toBeInTheDocument();
      expect(screen.getByText('Coverage: partial')).toBeInTheDocument();
      expect(screen.getByText('Action: retry')).toBeInTheDocument();
    });

    it("never renders a failed check as healthy and offers retry", async () => {
      vi.spyOn(dataQualityApi, "getConfidence").mockRejectedValue(new Error("offline"));
      show();
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to check data confidence.");
      expect(screen.queryByText(/Core data checks healthy/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });
  });

  describe("DrawdownEpisodes", () => {
    const episode: DrawdownEpisode = { id: "2026-01-01:2026-01-05", peak_date: "2026-01-01", trough_date: "2026-01-05",
      end_date: "2026-02-01", depth_pct: -20, recovery_date: "2026-02-01", recovery_interval_start: "2026-01-20",
      days_to_trough: 4, elapsed_days: 31, observations: 4 };
    it("labels observed recovery bounds and links a chart-only window without changing financial scope", () => {
      render(<MemoryRouter initialEntries={["/portfolio?tab=performance&account=ISA&period=YTD"]}>
        <DrawdownEpisodes available episodes={[episode]} />
      </MemoryRouter>);
      expect(screen.getByText("-20.00%")).toBeInTheDocument();
      expect(screen.getByText(/20 Jan 2026 – 1 Feb 2026/)).toBeInTheDocument();
      expect(screen.getByRole("link")).toHaveAttribute("href", "/portfolio?account=ISA&period=YTD&tab=performance&episode=2026-01-01%3A2026-01-05#performance-chart");
    });
    it("does not invent recovery for an unfinished episode", () => {
      render(<MemoryRouter><DrawdownEpisodes available episodes={[{ ...episode, recovery_date: null, recovery_interval_start: null }]} /></MemoryRouter>);
      expect(screen.getByText(/Not observed by 1 Feb 2026/)).toBeInTheDocument();
    });
    it("hides legacy episode numbers when the common chain is unavailable", () => {
      render(<MemoryRouter><DrawdownEpisodes available={false} episodes={[episode]}
        reasons={[{ code: "invalid_return_chain", message: "Broken interval.", action_href: null }]} /></MemoryRouter>);
      expect(screen.getByText("Broken interval.")).toBeInTheDocument();
      expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });
    it("distinguishes a valid flat history from unavailable data", () => {
      render(<MemoryRouter><DrawdownEpisodes available episodes={[]} /></MemoryRouter>);
      expect(screen.getByText("No observed drawdown episodes in this window.")).toBeInTheDocument();
    });
  });

  describe("GroupsSection", () => {
    const mk = (id: number): Instrument =>
      ({
        id,
        identifier: `T${id}`,
        security_name: `Name ${id}`,
        account_name: "Acct",
        is_cash: false,
        group_ids: [1],
      }) as Instrument;

    const group = {
      id: 1,
      name: "Core",
      target_allocation_pct: null,
      color: null,
      member_count: 2,
      total_value_gbp: 100,
    };

    const wrap = (node: ReactNode) => (
      <QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>
    );

    it("focusing and leaving unchanged targets never writes portfolio metadata", async () => {
      const update = vi.spyOn(api, "updateGroup").mockResolvedValue({} as never);
      render(wrap(<GroupsSection groups={[group]} instruments={[]} byGroup={{}} />));
      const input = screen.getAllByPlaceholderText("Target %")[1];
      await act(async () => {
        fireEvent.focus(input);
        fireEvent.blur(input);
      });
      expect(update).not.toHaveBeenCalled();
    });

    it("recovers membership checkboxes when instruments arrive after groups", async () => {
      const a = mk(1);
      const b = mk(2);
      const { rerender } = render(wrap(<GroupsSection groups={[group]} instruments={[]} byGroup={{}} />));
      rerender(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
      const boxes = screen.getAllByRole("checkbox");
      expect(boxes).toHaveLength(2);
      boxes.forEach((box) => expect(box).toBeChecked());
      expect(screen.getByText(/2 members/)).toBeInTheDocument();
    });

    it("keeps the user's pending checkbox edits when membership data refreshes", async () => {
      const a = mk(1);
      const b = mk(2);
      const { rerender } = render(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
      fireEvent.click(screen.getAllByRole("checkbox")[1]);
      rerender(wrap(<GroupsSection groups={[group]} instruments={[a, b]} byGroup={{ 1: [a, b] }} />));
      const boxes = screen.getAllByRole("checkbox");
      expect(boxes[0]).toBeChecked();
      expect(boxes[1]).not.toBeChecked();
    });
  });

  describe("OrderHistorySection", () => {
    it("renders backend total reasons rather than assuming missing amounts", () => {
      const page = { items: [], total_count: 0, offset: 0, limit: 100, has_more: false,
        totals: { buy_gbp: null, sell_gbp: 0, drip_gbp: 0 },
        totals_reasons: { buy_gbp: "non_finite_total" as const, sell_gbp: null, drip_gbp: null }, classification_basis: "Stored" };
      render(<OrderHistorySection page={page} pending={false} error={false} params={new URLSearchParams()} onChange={vi.fn()} onRetry={vi.fn()} />);
      expect(screen.getByText(/Full-filter totals/)).toHaveTextContent("Unavailable (non-finite total)");
    });

    it.each([
      ["Next page", 100, 200, false],
      ["Previous page", 100, 0, true],
    ] as const)("restores results focus after delayed %s from %s to %s", (name, offset, nextOffset, hasMore) => {
      const page: OrderPage = { items: [], total_count: 205, offset, limit: 100, has_more: true,
        totals: { buy_gbp: 25, sell_gbp: 0, drip_gbp: 0 }, totals_reasons: { buy_gbp: null, sell_gbp: null, drip_gbp: null }, classification_basis: "Stored" };
      const props = { page, pending: false, error: false, params: new URLSearchParams(), onChange: vi.fn(), onRetry: vi.fn() };
      const { rerender } = render(<OrderHistorySection {...props} />);
      const button = screen.getByRole("button", { name });
      button.focus();
      fireEvent.click(button);
      expect(props.onChange).toHaveBeenCalledWith("offset", String(nextOffset));
      rerender(<OrderHistorySection {...props} pending />);
      expect(screen.queryByText(/Full-filter totals/)).not.toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Order results" })).not.toBeInTheDocument();
      rerender(<OrderHistorySection {...props} page={{ ...page, offset: nextOffset, has_more: hasMore }} />);
      expect(screen.getByRole("region", { name: "Order results" })).toHaveFocus();
      if (!hasMore) expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    });
  });

  describe("TimelineEvents", () => {
    const events: TimelineEvent[] = [1, 2, 3].map((id) => ({ id: `${id === 3 ? "snapshot" : "order"}:${id}`, kind: id === 3 ? "snapshot" : "trade", date: "2026-01-10",
      occurred_at: id === 3 ? null : "2026-01-10T10:00:00", valuation_date: id === 3 ? "2026-01-10" : null, account_names: ["ISA"], instrument_id: 7,
      title: `Recorded event ${id}`, amount_gbp: id === 3 ? null : 10, source_type: id === 3 ? "import" : "order", source_id: id,
      source_href: `/activity?tab=source&source=${id === 3 ? "import" : "order"}&record=${id}&account=ISA&period=YTD`, details: {}, note: "Context, not causation." }));
    const data: TimelineResponse = { scope: { account_name: "ISA", requested_start: null, requested_end: null,
      effective_start: "2026-01-01", effective_end: "2026-02-01", valuation_dates: [], warnings: [] },
      events, event_count: 3, counts_by_kind: { trade: 2, snapshot: 1 }, notes: ["Import time is separate from valuation time."] };
    function show() {
      render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/portfolio?tab=holdings&account=ISA&period=YTD&inst=7"]}>
          <PreferencesContext.Provider value={{ accountFilter: "ISA", dripThreshold: 100, setAccountFilter: vi.fn(), setDripThreshold: vi.fn() }}>
            <AnalysisScopeContext.Provider value={{ period: "YTD", setPeriod: vi.fn() }}><TimelineEvents instrumentId={7} /></AnalysisScopeContext.Provider>
          </PreferencesContext.Provider>
        </MemoryRouter></QueryClientProvider>);
    }
    beforeEach(() => vi.clearAllMocks());
    it("groups same-day records, toggles categories and preserves context in source links", async () => {
      const request = vi.spyOn(timelineApi, "getTimeline").mockResolvedValue(data);
      show();
      fireEvent.click(await screen.findByText("10 Jan 2026 · 3 events"));
      expect(screen.getAllByRole("link")).toHaveLength(3);
      expect(screen.getByRole("link", { name: "View source order #1" })).toHaveAttribute("href", "/activity?account=ISA&period=YTD&inst=7&eventDate=2026-01-10&tab=source&source=order&record=1");
      expect(request).toHaveBeenCalledWith("ISA", "YTD", 7);
      fireEvent.click(screen.getByRole("checkbox", { name: "Trades (2)" }));
      expect(screen.getByText("10 Jan 2026 · 1 event")).toBeInTheDocument();
      expect(screen.getAllByRole("link")).toHaveLength(1);
    });
    it("reports failed event loading instead of a zero event count", async () => {
      vi.spyOn(timelineApi, "getTimeline").mockRejectedValue(new Error("offline"));
      show();
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load timeline events.");
      expect(screen.queryByText(/0 source-backed events/)).not.toBeInTheDocument();
    });
    it("provides a keyboard-operable chart marker with a dated accessible name", () => {
      const select = vi.fn();
      render(<svg><TimelineMarkerLabel viewBox={{ x: 100, y: 56 }} date="2026-01-10" count={3} number={1} width={320} onSelect={select} /></svg>);
      const marker = screen.getByRole("button", { name: "Timeline events on 2026-01-10: 3" });
      fireEvent.keyDown(marker, { key: "Enter" });
      fireEvent.keyDown(marker, { key: " " });
      expect(select).toHaveBeenCalledTimes(2);
      expect(select).toHaveBeenLastCalledWith("2026-01-10");
    });
  });
});

describe("PerformancePanel", () => {
  // Recharts renders SVG in jsdom (no layout); assert on the text we control.

  const basePerf: PerformanceSummary = {
    period: "ALL",
    coverage_start: null,
    period_start: "2026-01-01",
    period_end: "2026-02-01",
    start_value_gbp: 100,
    end_value_gbp: 200,
    total_return_pct: 100.0,
    annualised_return_pct: null,
    annualised_volatility_pct: null,
    sharpe_ratio: null,
    sortino_ratio: null,
    max_drawdown_pct: 0.0,
    max_drawdown_raw_pct: 0.0,
    best_period_return_pct: 100.0,
    worst_period_return_pct: 100.0,
    num_periods: 1,
    annualisation_factor: null,
    risk_free_annual_pct: 0,
    method: "arithmetic",
    notes: [],
    growth_curve: [
      { as_of_date: "2026-01-01", value_gbp: 100, normalized_value: 100 },
      { as_of_date: "2026-02-01", value_gbp: 200, normalized_value: 200 },
    ],
    benchmarks: [],
    flow_adjusted_curve: [
      { date: "2026-01-01", index: 100 },
      { date: "2026-02-01", index: 100 },
    ],
    drawdown_curve: [
      { date: "2026-01-01", index: 100, drawdown_pct: 0, at_peak: true },
      { date: "2026-02-01", index: 100, drawdown_pct: 0, at_peak: true },
    ],
    flow_adjusted: {
      contributions_gbp: 100,
      withdrawals_gbp: 0,
      net_external_flow_gbp: 100,
      total_return_pct: 0.0,
      annualised_return_pct: null,
      annualised_volatility_pct: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      num_periods: 1,
      annualisation_factor: null,
      method: "Modified Dietz",
      notes: ["flow-adjusted"],
      flow_adjusted_curve: [
        { date: "2026-01-01", index: 100 },
        { date: "2026-02-01", index: 100 },
      ],
      drawdown_curve: [
        { date: "2026-01-01", index: 100, drawdown_pct: 0, at_peak: true },
        { date: "2026-02-01", index: 100, drawdown_pct: 0, at_peak: true },
      ],
      max_drawdown_pct: 0.0,
    },
  };

  function renderPanel(ui: React.ReactNode, perfOverride?: PerformanceSummary) {
    const getPerformance = vi.fn(async () => perfOverride ?? basePerf);
    vi.spyOn(api, "getPerformance").mockImplementation(getPerformance);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const utils = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
    return { ...utils, getPerformance };
  }

  describe("PerformancePanel", () => {
    it('preserves the production compact period controls and description', async () => {
      renderPanel(<PerformancePanel compact />);
      await screen.findByText('Performance');
      expect(screen.getByRole('button', { name: '1M' })).toBeInTheDocument();
      expect(screen.queryByText(/Growth and risk for/)).not.toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Snapshot performance chart" })).toBeVisible();
    });
    it('omits routine caveats and reasons for metrics not shown in compact mode',async()=>{
      renderPanel(<PerformancePanel compact />, {...basePerf, metrics:{annualised_return_pct:{status:'unavailable',value:null,unit:'percent',method:'Dietz',start_date:null,end_date:null,observations:2,reasons:[{code:'short',message:'Custom annualisation unavailable.',action_href:null}]}}});
      await screen.findByText('Performance');
      expect(screen.queryByText('Custom annualisation unavailable.')).not.toBeInTheDocument();
      expect(screen.queryByText(/Trade-derived proxy flows/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Risk-free assumption/)).not.toBeInTheDocument();
    });
    it('keeps production metric tiles before the chart without adding an observation ledger',async()=>{
      renderPanel(<PerformancePanel />); await screen.findByText('Performance');
      const metric=screen.getByText('Snapshot investment return');
      const chart=screen.getByRole('region',{name:'Snapshot performance chart'});
      expect(Boolean(metric.compareDocumentPosition(chart)&Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
      expect(screen.queryByRole('table',{name:'Exact snapshot and drawdown observations'})).not.toBeInTheDocument();
    });
    it("keys requests by shared period and account and hides old metrics while the next scope loads", async () => {
      const request = vi.spyOn(api, "getPerformance").mockResolvedValue(basePerf);
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const panel = (account: string, period: "ALL" | "1M") => <QueryClientProvider client={client}>
        <AnalysisScopeContext.Provider value={{ period, setPeriod: vi.fn() }}>
          <PerformancePanel accountName={account} />
        </AnalysisScopeContext.Provider>
      </QueryClientProvider>;
      const view = render(panel("ISA", "ALL"));
      await screen.findByText("Performance");
      expect(request).toHaveBeenLastCalledWith("ISA", "ALL");
      request.mockImplementation(() => new Promise(() => {}));
      view.rerender(panel("Trading", "1M"));
      await screen.findByText("Crunching performance…");
      expect(request).toHaveBeenLastCalledWith("Trading", "1M");
      expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
    });
    it("honours unavailable metadata even when legacy payload contains curves and numbers", async () => {
      renderPanel(<PerformancePanel />, {
        ...basePerf,
        metrics: { annualised_return_pct: {status:"unavailable",value:null,unit:"percent",method:"Dietz",start_date:null,end_date:null,observations:2,reasons:[{code:"short",message:"Separate annualisation reason.",action_href:null}]}, total_return_pct: {
          status: "unavailable", value: null, unit: "percent", method: "Chain-linked Dietz",
          start_date: "2026-01-01", end_date: "2026-02-01", observations: 2,
          reasons: [{ code: "invalid_return_chain", message: "A correction left an unusable interval.", action_href: null }],
        } },
      });
      await screen.findByText("Performance");
      expect(screen.getAllByText("A correction left an unusable interval.").length).toBeGreaterThan(0);
      expect(screen.getByText("Separate annualisation reason.")).toBeVisible();
      expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
      expect(screen.queryByText("Flow-adjusted drawdown")).not.toBeInTheDocument();
      fireEvent.click(screen.getByLabelText(/Show raw account value/i));
      expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    });

    it("explains missing annualisation separately without hiding a valid cumulative chart", async () => {
      renderPanel(<PerformancePanel />, {
        ...basePerf,
        metrics: { annualised_return_pct: {
          status: "unavailable", value: null, unit: "percent", method: "Dietz",
          start_date: "2026-01-01", end_date: "2026-02-01", observations: 2,
          reasons: [{ code: "short_window", message: "Annualisation needs 365 days.", action_href: null }],
        } },
      });
      expect(await screen.findByText("Annualisation needs 365 days.")).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Snapshot performance chart" })).toBeInTheDocument();
      expect(screen.queryByText(/Typical:/)).not.toBeInTheDocument();
    });

    it("distinguishes the raw snapshots from those used for adjusted returns", async () => {
      const skippedNote = "One snapshot was skipped because the cash movement was not yet reflected.";
      renderPanel(<PerformancePanel compact />, {
        ...basePerf,
        growth_curve: [
          basePerf.growth_curve[0],
          { as_of_date: "2026-01-20", value_gbp: 100, normalized_value: 100 },
          basePerf.growth_curve[1],
        ],
        flow_adjusted: { ...basePerf.flow_adjusted!, notes: [skippedNote] },
      });
      expect(await screen.findByText("2 of 3 snapshots used")).toBeVisible();
      expect(screen.queryByText(skippedNote)).not.toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Snapshot performance chart" })).toBeInTheDocument();
    });

    it("never substitutes raw metrics when flow-adjusted metrics are unavailable", async () => {
      renderPanel(<PerformancePanel />, { ...basePerf, annualised_return_pct: 123, annualised_volatility_pct: 45, sharpe_ratio: 6, sortino_ratio: 7, flow_adjusted_curve: [], drawdown_curve: [], flow_adjusted: { ...basePerf.flow_adjusted!, total_return_pct: null, annualised_return_pct: null, annualised_volatility_pct: null, sharpe_ratio: null, sortino_ratio: null, flow_adjusted_curve: [], drawdown_curve: [] } });
      await screen.findByText("Performance");
      for (const label of ["Snapshot investment return", "Annualised", "Volatility", "Sharpe", "Sortino", "Max drawdown"]) {
        const tile = screen.getByText(label).parentElement!.parentElement!;
        expect(tile.querySelector("p.tabular")).toHaveTextContent("—");
      }
      expect(screen.getByText(/Flow-adjusted performance unavailable/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "About Snapshot investment return" }));
      expect(screen.getByRole("dialog")).toHaveTextContent("Chain-linked interval Modified Dietz");
      expect(screen.getByText("raw 100.00%")).toBeInTheDocument();
    });

    it("shows an explicit unavailable state when there is no curve", async () => {
      const empty: PerformanceSummary = {
        ...basePerf,
        growth_curve: [],
        flow_adjusted_curve: [],
        drawdown_curve: [],
        flow_adjusted: undefined,
      };
      renderPanel(<PerformancePanel />, empty);
      await waitFor(() =>
        expect(screen.getByText(/Not enough snapshot history yet/)).toBeInTheDocument(),
      );
    });

    it('preserves explicit invalid reasons even with no growth curve',async()=>{
      renderPanel(<PerformancePanel compact />, {...basePerf,growth_curve:[],metrics:{total_return_pct:{status:'unavailable',value:null,unit:'percent',method:'Dietz',start_date:null,end_date:null,observations:0,reasons:[{code:'correction',message:'Correction invalidates the entire chain.',action_href:null}]}}});
      expect(await screen.findByText('Correction invalidates the entire chain.')).toBeVisible();
    });
    it("cash-flow regression: pure contribution keeps the flow-adjusted drawdown at 0", async () => {
      // Raw value doubles (100 -> 200) from a single contribution with no market
      // gain; the flow-adjusted index is flat, so the KPI max drawdown is 0 and
      // the subline shows the raw drawdown distinctly.
      renderPanel(<PerformancePanel />);
      await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
      // The KPI tile's subline distinguishes the flow-adjusted value from the raw one.
      expect(screen.getByText("flow-adjusted · raw 0.00%")).toBeInTheDocument();
    });

    it("keeps the raw value overlay hidden by default and reveals it on toggle", async () => {
      const { container } = renderPanel(<PerformancePanel />);
      await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());

      // Default: raw value is not drawn and only the flow-adjusted legend is present.
      expect(screen.queryByText("Raw account value (index, optional)")).not.toBeInTheDocument();
      expect(screen.getByText(/Flow-adjusted \(index, 100 = window start\)/)).toBeInTheDocument();

      const toggle = screen.getByLabelText(/Show raw account value/i);
      fireEvent.click(toggle);
      expect(screen.getByText("Raw account value (index, optional)")).toBeInTheDocument();
      expect(container).toBeTruthy();
    });

    it("switches the main chart between the index view and absolute GBP", async () => {
      renderPanel(<PerformancePanel />);
      await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());

      // Default view is index-based with the 100 = start framing.
      expect(screen.getByRole("button", { name: "Index (100 = start)" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByText("Flow-adjusted (index, 100 = window start)")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Absolute (£)" }));
      expect(screen.getByRole("button", { name: "Absolute (£)" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByText("Flow-adjusted (£, flows excluded)")).toBeInTheDocument();
      expect(screen.queryByText("Flow-adjusted (index, 100 = window start)")).not.toBeInTheDocument();

      // The raw overlay also re-expresses itself in GBP.
      fireEvent.click(screen.getByLabelText(/Show raw account value/i));
      expect(screen.getByText("Raw account value (£, optional)")).toBeInTheDocument();
    });

    it("hides benchmark price indices from the £ view with an explanation", async () => {
      renderPanel(<PerformancePanel />, {
        ...basePerf,
        benchmarks: [
          { date: "2026-01-01", symbol: "ftse-100", value: 110 },
          { date: "2026-02-01", symbol: "ftse-100", value: 112 },
        ],
      });
      await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());

      expect(screen.getByText("FTSE-100 +12.0%")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Absolute (£)" }));
      expect(screen.queryByText("FTSE-100 +12.0%")).not.toBeInTheDocument();
      expect(screen.getByText("Benchmarks are price indices, shown only in the index view.")).toBeInTheDocument();
    });

    it("omits the scale switch when there is no positive start value to anchor GBP", async () => {
      for (const start of [null, 0, -50]) {
        const view = renderPanel(<PerformancePanel />, { ...basePerf, start_value_gbp: start });
        await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
        expect(screen.queryByRole("button", { name: "Absolute (£)" })).not.toBeInTheDocument();
        expect(screen.getByText("Flow-adjusted (index, 100 = window start)")).toBeInTheDocument();
        view.unmount();
      }
    });

    it("omits the scale switch while the flow-adjusted chain is unavailable even with a valid start value", async () => {
      renderPanel(<PerformancePanel />, {
        ...basePerf,
        start_value_gbp: 100,
        flow_adjusted_curve: [],
        drawdown_curve: [],
        flow_adjusted: { ...basePerf.flow_adjusted!, total_return_pct: null, flow_adjusted_curve: [], drawdown_curve: [] },
      });
      await waitFor(() => expect(screen.getByText("Performance")).toBeInTheDocument());
      expect(screen.queryByRole("button", { name: "Absolute (£)" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Index (100 = start)" })).not.toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Snapshot performance chart" })).not.toBeInTheDocument();
    });

    it("shows an error state without crashing", async () => {
      vi.spyOn(api, "getPerformance").mockRejectedValue(new Error("boom"));
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <PerformancePanel />
        </QueryClientProvider>,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load performance");
      expect(screen.queryByText(/Not enough snapshot history yet/)).not.toBeInTheDocument();
      vi.mocked(api.getPerformance).mockResolvedValue(basePerf);
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(await screen.findByText("Performance")).toBeInTheDocument();
    });
  });
});
