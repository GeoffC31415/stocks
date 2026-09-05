# Market-data validation and release gate

## Latest evidence — 2026-09-04: Yahoo sample works; release gate unvalidated

A later read-only probe successfully retrieved approximately two years of daily Yahoo history without a key/subscription. EQQQ.L returned 507 observations in GBp with an adjusted-close series present. A subsequent sequential batch returned:

| Symbol | Currency | Observations | Non-null adjusted closes |
|---|---|---:|---:|
| VUSD.L | USD | 507 | 505 |
| MU | USD | 502 | 502 |
| BA.L | GBp | 507 | 507 |
| VWRL.L | GBP | 507 | 504 |
| GBPUSD=X | USD per GBP | 524 | 519 |

Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d`. Batch requests were spaced two seconds apart with a stop-on-429 rule. Temporary batch evidence: `/tmp/stocks-free-data-probe/report.json` and corresponding responses; the separate EQQQ probe was not saved in that report. No live cache/database writes or package installations were performed.

**Interpretation:** Yahoo is now the recommended free first candidate for isolated full-portfolio backfill. Sample success does not prove provider terms, adjustment quality, valid aligned observations, specialist-fund mappings, or 80% value coverage. The production cache has not been populated by these probes; advanced-model release remains gated. Preserve missing-value, pence/pound, USD-listed London ETF, dated FX and valuation-date checks.

D01 in the [implementation plan](plans/2026-09-04-portfolio-experience.md) now specifies the Yahoo-first adapter, reproducible probe, isolated backfill, sparse refresh/backoff, offline-cache acceptance and validated manual CSV fallback. No paid source is assumed or authorised. Recheck provider data-use terms before persistent backfill.

## Earlier result — 2026-09-04: probe failed; gate not passed

The earlier 2026-09-02 notes declared the 80% gate passed after confirming only a subset of symbols. That conclusion was not supported by measured GBP value coverage. HTTP 429 responses are failures/unverified symbols, not evidence of available history.

Read-only verification of `portfolio.db` on 2026-09-04 found:

- 20 current holdings, including 19 non-cash holdings and one cash holding, spanning latest-date batches 31 and 33.
- Non-cash value £860,925.3281; cash £1,779.16; total £862,704.4881.
- Price cache: **0 rows**. FX cache: **0 rows**. Quote cache: **0 rows**.
- Verified usable coverage: **0%**; benchmark and historical FX depth: **0**.
- A bounded Yahoo probe using the correct standard-library opener interface requested `^GSPC` with a two-year daily window and received **HTTP 429**. It stopped immediately; other symbols were not assumed to work.
- An independent fresh Stooq request for `spy.us` returned HTTP 200 with an HTML JavaScript/browser-verification page, **not CSV price data**.
- No live database writes, refreshes or migrations were performed. The database hash was unchanged.

The Yahoo probe evidence and script are retained in `/tmp/stocks-provider-gate-20260904T212651Z/` and `/tmp/stocks-provider-gate-audit.py` for this session. These are temporary evidence paths, not a durable data source.

## Repairs made during the resumption

- Corrected `_http_get`: `urllib.request.OpenerDirector` provides `open`, not `urlopen`.
- `fetch_history` is now cache-only. Neither a cache miss nor a missing session triggers a provider call or database commit. Use the explicit refresh operation to fetch data.
- The unfinished risk service now uses same-date cached FX rather than a single latest exchange rate. GBP, GBp/GBX, USD and EUR are distinguished; unsupported currencies are excluded.
- The risk service's publication threshold is 126 aligned observations and 80% of **non-cash** value. These repairs do not certify the entire risk/forecast workstream.
- Risk factor identities are stable namespaced tickers/instrument IDs, independent of display names. All current exposures remain in the denominator; mismatched account valuation dates prevent publication with explicit warnings.
- The risk loader rejects inconsistent currencies and mixed adjusted/raw histories, excludes post-valuation observations and checks staleness of the actual aligned window. Non-finite holding inputs fail safely. The standalone Task 2 coverage report still needs the stricter validation listed below.

Offline regression tests exercise the real opener interface, cache-only misses, explicit refresh followed by cache reads, FX conversion and unavailable states. Synthetic test fixtures are not evidence that a live provider covers the portfolio.

## Work required before risk/scenarios can be released

1. Obtain a working provider/authorised data source and verify its terms for the intended storage/use. The earlier blanket claim that Yahoo local storage is permitted was not verified; do not treat it as a licence grant.
2. Explicitly map the application's legacy symbols (`spx.us`, `vwrl.uk`, `GOOGL.US`, `MU.US`) to provider symbols in the provider layer. Preserve requested identifiers in API metadata; do not silently guess fund-ISIN mappings.
3. Refresh an **isolated database first**, with machine-readable benchmark, holding and historical FX series; honour provider rate limits.
4. Harden the coverage report to require finite, valid price/FX observations, daily alignment and minimum history, not merely one cached close/latest FX rate. Disclose quote currency and adjustment policy per series.
5. Validate bounded refresh deadlines and cross-request single-flight behavior. The current sequential loop is not proof of process-wide concurrency control.
6. Prove at least 126 aligned daily observations and coverage of at least 80% of current non-cash GBP value; record exclusions and the complete current portfolio denominator.
7. Follow D01–D03 in the [Portfolio Experience and Insight Implementation Plan](plans/2026-09-04-portfolio-experience.md): validated history first, then risk and horizon-gated loss analysis, then separately gated bootstrap scenarios.

**Advanced risk and scenario releases remain blocked by this gate. A caching design alone cannot pass it.**
