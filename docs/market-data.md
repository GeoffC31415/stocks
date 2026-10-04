# Market data and analytical limits

Market history reads are cache-only. Cache misses or absent sessions do not authorize
provider requests or writes; fetching requires explicit refresh. Source contracts:
[market cache](../backend/app/services/market_data_service.py),
[portfolio risk](../backend/app/services/portfolio_risk_service.py) and
[cached prerequisites](../backend/app/services/data_quality_market.py).

Yahoo sample responses are not proof of full-portfolio coverage, permitted storage,
adjustment quality or production cache contents. Confirm provider terms before
persistent backfill, respect rate limits and stop/back off on refusal. Test on an
isolated database first; do not infer readiness from an old provider probe.

- Verify instrument/provider identifiers rather than guessing fund ISIN mappings.
- Distinguish GBP from GBp/GBX, USD and EUR; use dated, same-observation FX, not today's rate for history.
- Preserve quote currency and adjusted/raw basis; inconsistent currencies/bases,
  post-valuation data and stale aligned windows cannot support published analysis.
- Coverage includes all current non-cash value in its denominator, including exclusions.
  Missing/negative/nonfinite values prevent reliable coverage. Account valuation-date
  mismatches prevent publication.
- Cached prerequisites require at least **126 aligned daily observations** and
  **80% of non-cash GBP value**. `cache_gate_met` is not full provider/identity/benchmark
  acceptance: `validation_pending` remains true in the source contract.

Current-composition risk models today's holdings, not the investor's actual historical
portfolio. Benchmark comparability and horizons require separate evidence; synthetic
tests cannot validate live data. Scenario fans need accepted model assumptions in
addition to valid history/risk. Fund look-through requires constituent data, not product
classification or ticker matching. Missing inputs remain unavailable, never fabricated.
