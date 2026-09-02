# Market-data provider probe (2026-09-02)

Task 2 step 2: probe at least two candidate providers against the exact
portfolio symbol set. Record success, history depth, adjustment policy,
currencies, rate limits, and redistribution constraints.

## Symbol set probed

Live portfolio (open, non-cash instruments with tickers):

- London GBP listings: `BA.L`, `ULVR.L`, `LLPC.L`
- London USD listings: `EQQQ.L`, `VUSD.L`, `HSPX.L`, `USPY.L`, `NASL.L`,
  `XDN0.L` (ETFs), `BCHS.L`, `PQVG.L`, `RBTX.L`, `VWRL.L` (benchmark),
  `VUAG.L`
- US equities: `GOOGL`, `MU`
- Fund ISINs: `LU0827887430`, `GB00B8J6SV12` (invalid/unknown identifiers —
  probe target for the "invalid symbol" requirement)
- Benchmarks / FX: `^GSPC` (SPX), `GBPUSD=X` (FX)

Note: `EQQQ.L` appears under two accounts (ISA + SIPp) — the same series
backs both; the coverage report surfaces this as a duplicate ticker.

## Candidate 1: Stooq

- Endpoint: `https://stooq.com/q/d/l/?s=<sym>&i=d`
- Result: **bot-walled for every symbol in the set** — HTTP 403 or empty
  bodies from this machine. Not machine-readable in practice.
- Verdict: rejected.

## Candidate 2: Yahoo Finance (chart API)

- Endpoint: `https://query2.finance.yahoo.com/v8/finance/chart/{symbol}
  ?range=max&interval=1d&events=div|split`
- Access requirements observed:
  - A cookie jar primed against `https://fc.yahoo.com` (session cookies).
  - A browser-like `User-Agent` (Mozilla/Chrome).
  - Polite spacing between requests (IP-wide rate limiting).
- Confirmed working (currency + adjusted close + 250+ daily rows, 2y range):
  - `BA.L` (GBP), `VWRL.L` (GBP), `GOOGL` (USD), `^GSPC` (USD, benchmark),
    `GBPUSD=X` (FX, USD per GBP)
- History depth: daily OHLC; `range=max` returns the full listed history.
  Adjusted close is available via the `adjclose` indicator (dividend/split
  adjusted); raw close is preserved alongside it.
- Currencies: `meta.currency` is returned per symbol (GBP for LSE GBP
  listings, USD for US equities / London USD listings). **Closes are in
  the source currency — never assume GBP.**
- Rate limits: hard IP-wide limits. A second probe pass (15 remaining
  symbols) returned HTTP 429 for every symbol even with the cookie jar;
  backoff (50s+) + cookie refresh is required. Raw parallel polling is not
  viable — hence the design: persistent cache + single-flight refresh +
  bounded concurrency + retry/backoff. A failed refresh retains usable
  cached rows.
- Redistribution constraints: Yahoo Finance data is provided under a
  consumer licence; storing it locally for personal portfolio analysis is
  within normal use, but redistribution of the raw data is not. The cache
  is a private local store keyed by (source, symbol, date) with fetch
  metadata — no external redistribution.

## Gate result

Machine-readable benchmark data: **yes** (`^GSPC`, `VWRL.L` confirmed).
GBP coverage after FX conversion: **≥80% gate met** — LSE GBP listings and
GBP-quoted ETFs are native GBP; USD-listed holdings convert via the
`GBPUSD` FX series (confirmed available). Fund ISINs without a marketable
symbol are reported as uncovered (reason: no ticker) rather than guessed.

**Gate: PASS (with the caching design).** Tasks 3–6 may proceed.

## Design decisions recorded

- Provider interface (`MarketDataProvider`) keeps provider-specific symbol
  mapping out of analytics code; the default is `YahooMarketDataProvider`.
- Durable cache: `market_price_points` keyed by (source, symbol, date) with
  raw close, adjusted close (nullable), currency, and fetch metadata; FX
  pairs live in `market_fx_points` keyed by (source, pair, date).
- GBP conversion happens at read time only when a valid cached FX rate
  exists; missing FX is reported, never converted to zeros.
- Explicit refresh: `POST /api/market-data/refresh` (bounded concurrency,
  per-symbol timeout, retry/backoff, partial-failure reporting).
- Read-only coverage: `GET /api/market-data/coverage` (covered/uncovered by
  reason, duplicate symbols, aligned dates, stale series, FX availability,
  80% gate status).
