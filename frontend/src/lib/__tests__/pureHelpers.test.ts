// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { legacyRedirectUrl } from "../../routing";
import { holdingPerformanceSignals } from "../../components/holdingSignals";
import { api, type Instrument, type Order } from "../api";
import { categoryColor, chartTheme } from "../chartTheme";
import { compactGbp, formatOrderDate, pct, signedGbp, toGbp, toGbpExact } from "../formatters";
import { filterHoldings, holdingDisplayName, parseInstrumentId, sortHoldings } from "../holdingsView";
import { instrumentBuyMarkerDates, instrumentSellMarkerDates } from "../instrumentBuyMarkers";
import { holdingsLink, ordersLink } from "../investigationLinks";
import { orderPageParams } from "../orderPageApi";
import { absoluteGbpDomain, absoluteGbpTicks, indexToGbp, joinPerformanceSeries, performanceIndexDomain, performanceIndexTicks, rebaseRowsToGbp, sparseDateTicks } from "../performanceChart";
import { chartUtcMs } from "../chartDates";
import { latestTaxYear, selectTaxYear } from "../../routes/cgtPresentation";

describe("routing", () => {
  describe("legacyRedirectUrl", () => {
    it("preserves deep-link parameters while selecting the new workspace tab", () => {
      expect(legacyRedirectUrl("/portfolio", "holdings", "?inst=42")).toBe(
        "/portfolio?inst=42&tab=holdings",
      );
      expect(legacyRedirectUrl("/activity", "changes", "?from=2&to=3")).toBe(
        "/activity?from=2&to=3&tab=changes",
      );
    });
  });
});

describe("holdingSignals", () => {
  describe("holdingPerformanceSignals", () => {
    it("describes evidence without issuing buy or sell instructions", () => {
      const labels = holdingPerformanceSignals({
        latestPctChange: 42.5,
        drawdownFromPeakPct: -2.1,
        quantityUnchangedSnapshotCount: 4,
      }).map((signal) => signal.label);

      expect(labels).toContain("42.50% gain · 2.1% below peak");
      expect(labels.join(" ").toLowerCase()).not.toMatch(/trim|top.?up|buy|sell/);
    });

    it("describes a sustained loss neutrally", () => {
      expect(
        holdingPerformanceSignals({
          latestPctChange: -15,
          drawdownFromPeakPct: -18,
          quantityUnchangedSnapshotCount: 3,
        }),
      ).toContainEqual({ label: "-15.00% P&L · quantity unchanged for 3 snapshots", tone: "rose" });
    });
  });
});

describe("allocationApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("requests the selected allocation dimension and URL-encodes the account", async () => {
    const payload = { dimension: "currency", totalValue: 104 };
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetcher);
    expect(await api.getAllocation("currency", "ISA & SIPP")).toEqual(payload);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/portfolio/allocation?dimension=currency&group_by=security&account_name=ISA+%26+SIPP", expect.objectContaining({credentials:'same-origin', signal:expect.any(AbortSignal)}),
    );
  });

  it("surfaces allocation endpoint errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, json: async () => ({ detail: "Allocation unavailable" }),
    }));
    await expect(api.getAllocation()).rejects.toThrow("Allocation unavailable");
  });

  it("sends explicit position grouping without changing account scope", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetcher);
    await api.getAllocation("account", "ISA", "position");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/portfolio/allocation?dimension=account&group_by=position&account_name=ISA", expect.objectContaining({credentials:'same-origin', signal:expect.any(AbortSignal)}),
    );
  });
});

describe("chartTheme", () => {
  describe("stable category colours", () => {
    it("does not recolour surviving categories on sorting/filtering", () => {
      const categories = ["Equity", "Bonds", "Other"];
      const original = Object.fromEntries(categories.map((name) => [name, categoryColor("asset_class", name)]));
      for (const name of [...categories].reverse().slice(1)) expect(categoryColor("asset_class", name)).toBe(original[name]);
    });
    it("always makes Unclassified explicit and includes dimension in identity", () => {
      expect(categoryColor("region", "Unclassified")).toBe(chartTheme.uncertainty);
      expect(categoryColor("asset_class", "Other")).not.toBe(categoryColor("region", "Other"));
    });
  });
});

describe("formatters", () => {
  describe("financial display formats (never calculation inputs)", () => {
    it("distinguishes missing values from real zero", () => {
      expect(toGbp(null)).toBe("—");
      expect(pct(undefined)).toBe("—");
      expect(toGbp(0)).toBe("£0");
      expect(toGbp(Infinity)).toBe("—");
    });
    it("keeps legacy whole-pound rounding and offers exact detail", () => {
      expect(toGbp(1234.56)).toBe("£1,235");
      expect(toGbpExact(1234.56)).toBe("£1,234.56");
      expect(toGbp(-0.1)).toBe("£0");
      expect(toGbpExact(-0.001)).toBe("£0.00");
      expect(pct(-0.001)).toBe("0.00%");
    });
    it("uses compact axes including millions and explicit signed outcomes", () => {
      expect(compactGbp(250000)).toBe("£250k");
      expect(compactGbp(1000000)).toBe("£1m");
      expect(signedGbp(1234.5)).toBe("+£1,235");
      expect(signedGbp(-1234.5)).toBe("−£1,235");
      expect(signedGbp(-0.1)).toBe("£0");
      expect(signedGbp(null)).toBe("—");
    });
    it("formats dates consistently in UTC and handles invalid dates", () => {
      expect(formatOrderDate("2026-01-01T00:30:00Z")).toBe("1 Jan 2026");
      expect(formatOrderDate("not a date")).toBe("—");
    });
  });
});

describe("groupScope", () => {
  afterEach(()=>vi.unstubAllGlobals());
  it('requests authoritative account-scoped group performance',async()=>{const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>[]});vi.stubGlobal('fetch',fetcher);await api.getGroupPerformance(1000,'ISA & savings');expect(String(fetcher.mock.calls[0][0])).toContain('account_name=ISA+%26+savings');});
});

describe("holdingsView", () => {
  const rows = [{id:1, security_name:'Alpha fund', identifier:'broker-1', ticker:'AAA', account_name:'ISA', group_ids:[2], sector:'Tech', latest_value_gbp:-2}, {id:2, security_name:'Beta', identifier:'broker-2', ticker:'BBB', account_name:'SIPP', group_ids:[], sector:null, latest_value_gbp:null}] as Instrument[];
  describe('holdings view', () => {
   it('bounds no-ticker display without changing searchable source identity',()=>{
    const name='A very long original broker security name containing share class and accumulation currency suffix';
    const fund={...rows[0],ticker:null,security_name:name};
    expect(holdingDisplayName(fund).length).toBeLessThanOrEqual(48);
    expect(holdingDisplayName(fund)).toBe('A very long original broker security name…');
    expect(fund.security_name).toBe(name);
    expect(filterHoldings([fund],new URLSearchParams({q:'accumulation currency suffix'})).rows).toEqual([fund]);
   });
   it.each(['constructor','toString','__proto__'])('rejects inherited dimension %s', dimension => {
    const result=filterHoldings(rows,new URLSearchParams({category_dimension:dimension,category:'Unknown'}));
    expect(result.error).toBeTruthy(); expect(result.rows).toEqual([]);
   });
   it('rejects noncanonical and duplicate detail ids', () => {
    for (const raw of ['01','1e2','0','-1','1.0',' 1','9007199254740992','1&inst=2']) expect(parseInstrumentId(new URLSearchParams('inst='+raw))).toBeNull();
    expect(parseInstrumentId(new URLSearchParams('inst=1'))).toBe(1);
   });
   it('searches ticker, source name and identifier and applies explicit filters', () => {
    for(const q of ['AAA','Alpha','broker-1']) expect(filterHoldings(rows,new URLSearchParams({q})).rows.map(i=>i.id)).toEqual([1]);
    expect(filterHoldings(rows,new URLSearchParams('category_dimension=sector&category=Tech&group=2&instrument_ids=1')).rows).toHaveLength(1);
    for(const q of ['instrument_ids=01','group=abc','category_dimension=bad&category=Tech','category=Tech','instrument_ids=1,,2']) {
     expect(filterHoldings(rows,new URLSearchParams(q)).error).toBeTruthy();
     expect(filterHoldings(rows,new URLSearchParams(q)).rows).toEqual([]);
    }
    expect(filterHoldings(rows,new URLSearchParams('category_dimension=sector&category=unknown')).rows).toEqual([]);
   });
   it('keeps missing numeric values last in both directions', () => {
    expect(sortHoldings(rows,'value','asc').map(i=>i.id)).toEqual([1,2]);
    expect(sortHoldings(rows,'value','desc').map(i=>i.id)).toEqual([1,2]);
   });
  });
});

describe("instrumentBuyMarkers", () => {
  const order = (id: number, side: string, is_drip: boolean, order_date: string) => ({
    id, side, is_drip, order_date,
  } as Order);

  describe("instrumentBuyMarkerDates", () => {
    it("returns sorted unique UTC calendar dates for non-DRIP buys only", () => {
      const markers = instrumentBuyMarkerDates([
        order(1, "Buy", false, "2026-02-02T15:30:00"),
        order(2, "buy", false, "2026-01-10"),
        order(3, "BUY", false, "2026-01-10T09:00:00Z"),
        order(4, "Buy", true, "2026-01-15"),
        order(5, "Sell", false, "2026-01-20"),
        order(6, "Buy", false, "not-a-date"),
      ]);

      expect(markers).toEqual([Date.UTC(2026, 0, 10), Date.UTC(2026, 1, 2)]);
    });

    it("returns sorted unique calendar dates for sells without treating buys as sales", () => {
      const markers = instrumentSellMarkerDates([
        order(1, "Sell", false, "2026-03-10T15:30:00"),
        order(2, "sell", false, "2026-02-05"),
        order(3, "SELL", false, "2026-02-05T09:00:00Z"),
        order(4, "Buy", false, "2026-01-15"),
        order(5, "Sell", false, "not-a-date"),
      ]);

      expect(markers).toEqual([Date.UTC(2026, 1, 5), Date.UTC(2026, 2, 10)]);
    });
  });
});

describe("investigationLinks", () => {
  it('preserves encoded account, period and comparison while replacing stale focus',()=>{const url=holdingsLink('?period=1Y&from=2&to=8&inst=99&q=stale',{account:'ISA & savings',instrumentIds:[1,3],category:{dimension:'currency',label:'USD'}});const p=new URL(url,'http://test').searchParams;expect(p.get('account')).toBe('ISA & savings');expect(p.get('period')).toBe('1Y');expect(p.get('from')).toBe('2');expect(p.get('inst')).toBeNull();expect(p.get('q')).toBeNull();expect(p.get('instrument_ids')).toBe('1,3');expect(p.get('allocation_category')).toBe('USD');});
  it('orders target the exact group/instrument and matching transaction dates',()=>{const url=ordersLink('?account=ISA&period=6M&group_ids=8&offset=100&search=stale',{instrumentId:3,fromDate:'2025-01-01',toDate:'2025-02-28',kind:'drip'});const p=new URL(url,'http://test').searchParams;expect(p.get('inst')).toBe('3');expect(p.get('group_ids')).toBeNull();expect(p.get('offset')).toBe('0');expect(p.get('search')).toBeNull();expect(p.get('period')).toBe('6M');expect(p.get('from_date')).toBe('2025-01-01');expect(p.get('kind')).toBe('drip');});
  it('refuses noncanonical numeric identifiers rather than repairing them',()=>{expect(()=>holdingsLink('',{instrumentId:NaN})).toThrow();expect(()=>holdingsLink('',{instrumentIds:[]})).toThrow();expect(()=>ordersLink('',{instrumentId:-1})).toThrow();});
});

describe("orderPageApi", () => {
  it("preserves repeated instrument/group filters and exact account without leaking performance scope", () => {
    const query = orderPageParams(new URLSearchParams("offset=100&instrument_ids=2&instrument_ids=3&group_ids=7&from_date=2026-01-01&period=1Y&tab=orders"), "ISA & pension");
    expect(query.getAll("instrument_ids")).toEqual(["2", "3"]);
    expect(query.getAll("group_ids")).toEqual(["7"]);
    expect(query.get("account_name")).toBe("ISA & pension");
    expect(query.get("offset")).toBe("100");
    expect(query.get("from_date")).toBe("2026-01-01");
    expect(query.has("period")).toBe(false);
    expect(query.has("tab")).toBe(false);
  });
});

describe("performanceChart", () => {
  describe("performance presentation geometry", () => {
    it("joins named series at one timestamp without losing valid values", () => {
      const rows = joinPerformanceSeries({
        flow: [{ date: "2026-01-01", index: 100 }, { date: "2026-02-01", index: 110 }],
        raw: [{ as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 100 },
          { as_of_date: "2026-01-01", normalized_value: null, value_gbp: null }],
        benchmarks: [{ date: "2026-01-01", symbol: "A.B", value: 101 }],
      });
      expect(rows).toHaveLength(2);
      expect(rows[0]).toEqual({ chartTime: chartUtcMs("2026-01-01"), flowAdjusted: 100,
        rawValue: 100, rawGbp: 100, "benchmark:A.B": 101 });
    });
    it("does not conflate punctuation in benchmark identity or invent missing values", () => {
      const rows = joinPerformanceSeries({ flow: [], raw: [], benchmarks: [
        { date: "2026-01-01", symbol: "A.B", value: 101 },
        { date: "2026-01-01", symbol: "A_B", value: 102 },
        { date: "invalid", symbol: "A_B", value: 103 },
      ] });
      expect(rows).toHaveLength(1);
      expect(rows[0]["benchmark:A.B"]).toBe(101);
      expect(rows[0]["benchmark:A_B"]).toBe(102);
      expect(rows[0].flowAdjusted).toBeUndefined();
    });
    it("selects sparse unique ticks by pixel distance, not observation rank", () => {
      const days = [1, 1, 2, 3, 4, 5, 30].map((day) => chartUtcMs(`2026-01-${String(day).padStart(2, "0")}`));
      expect(sparseDateTicks(days, 200)).toEqual([days[0], days[days.length - 1]]);
      const ticks = sparseDateTicks(days, 800);
      expect(new Set(ticks).size).toBe(ticks.length);
      expect(ticks.length).toBeLessThan(days.length - 1);
      expect(sparseDateTicks([], 300)).toEqual([]);
    });
    it("anchors clean dynamic performance ticks at 100", () => {
      expect(performanceIndexTicks([98.6, 106.6, 114.6])).toEqual([100, 110, 120]);
      expect(performanceIndexTicks([70, 100, 135])).toContain(100);
    });
    it("keeps baseline 100 and extrema in the index domain", () => {
      const [min, max] = performanceIndexDomain([0, 90, 104, 1000]);
      expect(min).toBeLessThanOrEqual(0);
      expect(max).toBeGreaterThanOrEqual(1000);
      const flat = performanceIndexDomain([100, 100]);
      expect(flat[0]).toBeLessThan(100);
      expect(flat[1]).toBeGreaterThan(100);
    });
    it("re-expresses the joined series in absolute GBP for the £ view", () => {
      const joined = joinPerformanceSeries({
        flow: [{ date: "2026-01-01", index: 100 }, { date: "2026-02-01", index: 110 }],
        raw: [
          { as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 2000 },
          { as_of_date: "2026-02-01", normalized_value: 105, value_gbp: 2100 },
        ],
        benchmarks: [{ date: "2026-01-01", symbol: "FTSE 100", value: 101 }, { date: "2026-02-01", symbol: "FTSE 100", value: 102 }],
      });
      const rebased = rebaseRowsToGbp(joined, 2000, ["FTSE 100"]);
      // The first point lands exactly on the window start value (index 100).
      expect(rebased[0].flowAdjusted).toBe(2000);
      // A 10% index gain scales the start value by 10%.
      expect(rebased[1].flowAdjusted).toBe(2200);
      // The raw overlay switches to the real snapshot GBP values.
      expect(rebased.map((row) => row.rawValue)).toEqual([2000, 2100]);
      // Price indices have no GBP equivalent and are nulled out.
      expect(rebased.map((row) => row["benchmark:FTSE 100"])).toEqual([null, null]);
      // Timestamps survive the rebase.
      expect(rebased.map((row) => row.chartTime)).toEqual(joined.map((row) => row.chartTime));
    });
    it("returns rows unchanged when there is no usable GBP anchor", () => {
      const joined = joinPerformanceSeries({
        flow: [{ date: "2026-01-01", index: 100 }],
        raw: [{ as_of_date: "2026-01-01", normalized_value: 100, value_gbp: 2000 }],
        benchmarks: [],
      });
      for (const start of [0, -5, null, Number.NaN]) {
        expect(rebaseRowsToGbp(joined, start, [])).toBe(joined);
      }
    });
    it("converts a chain-linked index to GBP using the window start value", () => {
      expect(indexToGbp(100, 1000)).toBe(1000);
      expect(indexToGbp(112.5, 800)).toBe(900);
      expect(indexToGbp(110, 1000.5)).toBe(1100.55);
      expect(indexToGbp(null, 1000)).toBeNull();
      expect(indexToGbp(110, null)).toBeNull();
      expect(indexToGbp(110, 0)).toBeNull();
      expect(indexToGbp(110, Number.NaN)).toBeNull();
    });
    it("pads absolute GBP domains and pads flat series by a fraction of the value", () => {
      const [low, high] = absoluteGbpDomain([98, 104, 1000]);
      expect(low).toBeLessThan(98);
      expect(high).toBeGreaterThan(1000);
      const [flatLow, flatHigh] = absoluteGbpDomain([100000, 100000]);
      expect(flatLow).toBeLessThan(100000);
      expect(flatHigh).toBeGreaterThan(100000);
      expect(absoluteGbpDomain([])).toEqual([0, 1]);
    });
    it("emits clean 1-2-5 GBP ticks with no 100 anchor", () => {
      expect(absoluteGbpTicks([98, 104, 1000]).every((t) => Number.isFinite(t))).toBe(true);
      const small = absoluteGbpTicks([1000, 2500]);
      expect(small.length).toBeGreaterThanOrEqual(2);
      const step = small[1] - small[0];
      const magnitude = 10 ** Math.floor(Math.log10(step));
      expect([1, 2, 5, 10].includes(step / magnitude)).toBe(true);
      expect(small[0]).toBeGreaterThanOrEqual(1000);
      expect(absoluteGbpTicks([])).toEqual([]);
    });
  });
});

describe("cgtPresentation", () => {
  describe("latestTaxYear", () => {
    it("returns the latest available tax year even when rows are unsorted", () => {
      expect(
        latestTaxYear([
          { tax_year: "2025-26" },
          { tax_year: "2023-24" },
          { tax_year: "2026-27" },
          { tax_year: "2024-25" },
        ]),
      ).toBe("2026-27");
    });

    it("returns null when no tax years are available", () => {
      expect(latestTaxYear([])).toBeNull();
    });
  });

  describe("selectTaxYear", () => {
    const rows = [
      { tax_year: "2023-24", taxable_gain: 7000 },
      { tax_year: "2024-25", taxable_gain: 4000 },
    ];

    it("returns only the explicitly selected tax year's row", () => {
      expect(selectTaxYear(rows, "2023-24")?.taxable_gain).toBe(7000);
    });

    it("defaults to the latest row when no valid selection exists", () => {
      expect(selectTaxYear(rows, null)?.taxable_gain).toBe(4000);
      expect(selectTaxYear(rows, "2022-23")?.taxable_gain).toBe(4000);
    });
  });
});
