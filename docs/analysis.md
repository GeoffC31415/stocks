# Analysis semantics


### Current state, performance and risk are different

- **Current holdings:** latest snapshots for the selected accounts. Check dates, missing account coverage and cash treatment before comparing totals.
- **Actual-portfolio performance:** a snapshot-boundary, flow-adjusted Modified Dietz estimate. Dietz is an estimated money-weighted method, not exact time-weighted return. Observe the disclosed covered dates and whether a figure is cumulative or annualised.
- **Position gain/cost:** unrealised gain against recorded book cost. Lifetime position MWR includes transaction timing; neither is interchangeable with selected-period portfolio performance.
- **Past holdings valued at today’s prices:** order-derived quantities valued at current prices. This renamed reconstruction is not historical portfolio wealth, benchmarked actual return, or a valid performance benchmark overlay.
- **Current-composition risk:** historical modelling of today's holdings, not a record of what the investor actually held. Missing history must remain unavailable, not replaced with fabricated analytics.
- **All-account history:** the Dashboard retains the longest available account history. When an account first appears, its first observed value is added as a scope baseline rather than being treated as investment return; subsequent changes participate normally. This makes the return representative over the full available period while clearly distinguishing account-scope additions from market performance.

For accounts with successfully synced Trading 212 cash history, external flows are actual API deposits less withdrawals; purchases and sales are internal and are not counted again. Other accounts retain observed non-DRIP buy contribution proxies and sale withdrawal proxies where retained cash cannot be distinguished from money leaving the account. The residual after observed flows and reinvestment is **not pure price effects**: FX, fees, missing transactions, timing and valuation differences can contribute. Holding contribution attribution is not a causal price decomposition.

The shared period applies to Performance. Holdings, allocation and groups use latest snapshots; Returns uses lifetime transactions. Income uses its own calendar comparison and trailing windows; Tax uses the chosen tax year; Changes uses the selected snapshot pair. Matching/classification repair queues may span all accounts. Orders has its own search and `from_date`/`to_date` filters. Full-filter totals cover all matching orders independently of pagination; changing the query must update totals, while changing only the page must not redefine their scope.

### Security identity, concentration and targets

Security aggregation is conservative. The reviewed registry currently approves only EQQQ with exact ISIN `IE0032077012` or SEDOL `B0GL4T3`, listing `EQQQ` on `XLON`, provider mapping `EQQQ.L`, and supported source value currency `GBP`/`GBX`/`GBp`. The unchanged source currency remains part of the key. Similar names or editable tickers cannot merge unsupported identifiers, listings, currencies or share classes. Broker records are not rewritten. See [reviewed identity evidence](security-identity.md).

HHI measures displayed weight concentration, **not diversification or fund overlap**. Product-level classifications are not constituent look-through. Two apparently separate funds can own the same underlying companies.

Target comparison requires a complete, exclusive target set: every eligible holding belongs to exactly one group, targets sum to **100% within ±0.01 percentage points**, and the cash-excluded invested scope has positive value. Invalid/overlapping/incomplete sets are unavailable, not silently normalised. Drift is measured in percentage points; personal tolerance is a user preference, not investment advice.

Contribution scenarios use hypothetical user-entered amounts. They execute no trades, transfer no money, and do not change holdings or real cash. Cash is excluded from the model; a result is not a funded order or recommendation.

### Income is a purchase proxy

Income uses **backend-stored import classification**, not a retrospective application of today's threshold. Threshold changes do not rewrite historical purchases. Reinvestment purchases are not declared/cash dividends and are not a complete dividend ledger.

Matched YTD compares the current calendar period with the same prior-year calendar period, not a partial current year with a complete prior year. February 29 is clamped to February 28 when the prior year has no leap day. Check the comparison endpoint and latest recorded transaction date. Completeness remains unknown; months without recorded purchases are `null` (displayed as unavailable/dash), not confirmed zero income.

Drivers retain current, closed and unlinked records. Current/closed status uses latest snapshots independently of the comparison period. Matching-purchase links carry account, instrument, stored DRIP kind and applicable dates into Orders; unlinked rows lead to their source records. Orders uses `kind=drip`, not `type=drip`.

### Repair workflow

Start at Data confidence; identify affected accounts, dates and source records. Verify the broker file and import coverage, then resolve only evidenced matching/classification exceptions. Review the source account because repair queues can include all accounts. Keep a verified private backup before imports or bulk changes, refresh derived data afterward, and recheck confidence. Healthy matching alone does not prove complete cash-flow, market-history or income coverage.

