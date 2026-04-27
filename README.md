# Portfolio Tracker (Barclays XLS)

Track and visualize your stock portfolio over time by importing the two `.xls` exports Barclays Stockbrokers makes available:

- `LoadDocstore.xls` / `Portfolio.xls` — point-in-time **portfolio snapshot** (holdings, qty, price, value, book cost, % change).
- `OrderHistory.xls` — your full **order history** (buys, sells, DRIP).

Each snapshot is hashed, deduplicated and persisted, so over time you accumulate a series of snapshots you can diff, chart and use to attribute performance back to actual cash flows.

The goal: clearly see how your portfolio has changed between imports and surface enough context (P&L, CAGR, DRIP vs. discretionary, best/worst movers) to inform what to buy or sell next.

---

## Stack

- **Backend** — FastAPI, Pydantic v2, SQLAlchemy 2 (async), SQLite (`portfolio.db` in repo root)
- **XLS parsing** — `python-calamine` (handles the legacy Barclays `.xls`)
- **Frontend** — React 19 + TypeScript + Vite, Tailwind, TanStack Query, Recharts, Framer Motion, lucide-react
- **Routing** — React Router 7

In production the FastAPI app also serves the built frontend from `frontend/dist`.

---

## Quick start

1. Backend virtualenv + deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Frontend deps:

```bash
cd frontend && npm install && cd ..
```

3. Run both dev servers (in separate shells):

```bash
./start_backend.sh     # uvicorn on :8000
./start_frontend.sh    # vite on :5173 (proxies /api → :8000)
```

Open http://localhost:5173.

To serve everything from a single port, build the frontend (`npm run build`) and run only the backend — `app.main` mounts `frontend/dist` at `/`.

---

## Importing data

### Web UI (`/import`)

Two tabs:

- **Portfolio snapshot** — pick a `LoadDocstore.xls`. The snapshot date defaults to the file's last-modified date, but you can override it. `force` lets you re-import a file with the same hash.
- **Order history** — pick an `OrderHistory.xls`. Set the **DRIP threshold** in the topbar; buys below it are flagged as dividend reinvestments.

### CLI

```bash
cd backend
../.venv/bin/python -m app.import_cli ../data/LoadDocstore.xls
```

Optional flags: `--as-of-date YYYY-MM-DD`, `--force`.

---

## What you get

### `/` Overview
- Hero KPI: latest **portfolio value** with 12-month sparkline + Δ vs. a year ago.
- **P&L**, **effective return** (value + sales − cash deployed), **annualised CAGR**, **cash deployed**, **DRIP reinvested**, **sale proceeds**.
- Three charts (tabs): historical estimate (order-derived qty × current prices), capital deployment, and snapshot history.
- Performance leaders: best/worst % movers in the latest snapshot.

### `/holdings`
- Searchable, sortable table of every instrument in the latest snapshot.
- Click a row to open instrument detail: full historical value/book-cost line chart and the matched orders.

### `/positions`
- Per-security cost basis, DRIP, sells, net cost, current value, estimated P&L and **CAGR**, all derived from order history.
- Open vs. closed tabs; closed tab totals realised P&L.

### `/orders`
- Full order log with DRIP classification and stat cards.

### `/groups`
- Tag instruments with user-defined groups (e.g. "ETFs", "UK income"). Groups feed back into the Overview's `by_group` allocation.

### `/import`
- Upload + recent imports list with new / closed counts per batch.

---

## Project structure

```
backend/app/
  main.py                      # FastAPI app, lifespan, static mount
  config.py                    # pydantic-settings
  database.py                  # async engine + tiny inline migration
  models.py                    # SQLAlchemy 2 ORM
  schemas.py                   # Pydantic v2 IO models
  import_cli.py                # CLI snapshot importer
  routers/                     # imports, orders, portfolio, instruments, groups
  services/
    barclays_parser.py         # snapshot XLS → ParsedHoldingRow[]
    barclays_order_parser.py   # order-history XLS → ParsedOrderRow[]
    import_service.py          # snapshot ingest + diff vs. previous batch
    order_service.py           # analytics, cashflow, positions, CAGR
    instrument_matcher.py      # links Order.security_name → Instrument
    order_fingerprint.py       # stable hash → de-dupe orders across imports
    portfolio_service.py       # summary + timeseries
frontend/src/
  layout/                      # AppShell, Sidebar, Topbar (DRIP threshold)
  routes/                      # Overview, Holdings, Positions, Orders, Groups, Import
  components/                  # KPIs, charts, tables, panels
  lib/api.ts                   # typed fetch client
  state/usePreferences.ts      # localStorage-backed prefs
data/                          # sample Portfolio.xls / OrderHistory.xls
portfolio.db                   # SQLite (gitignored)
```

---

## Data model (high level)

- `import_batches` — one row per portfolio snapshot import, with `file_sha256` (dedupe), `as_of_date`, and a JSON `diff_summary` of new / changed / closed instruments vs. the previous batch.
- `instruments` — unique by `(account_name, identifier)`. `closed_at` is set automatically when an instrument disappears from a newer snapshot.
- `holding_snapshots` — per-instrument values for a batch (qty, last price, value GBP, book cost GBP, % change).
- `order_import_batches` + `orders` — order history, deduped at row level via `order_fingerprint` (stable SHA over the row's economic identity).
- `instrument_groups` + `instrument_group_members` — user-defined grouping.

---

## API surface (selected)

```
POST   /api/imports                         # snapshot upload
GET    /api/imports                         # snapshot batches (newest first)
POST   /api/orders/import                   # order-history upload
GET    /api/orders                          # order log
GET    /api/orders/analytics                # totals, DRIP split, annual DRIP
GET    /api/orders/cashflow-timeseries      # monthly/cumulative net deployed
GET    /api/orders/positions                # cost basis + CAGR per security
GET    /api/orders/estimated-timeseries     # qty × current price by month
POST   /api/orders/backfill-instruments     # re-match unlinked orders
GET    /api/portfolio/summary               # totals, by_account, by_group, best/worst
GET    /api/portfolio/timeseries            # value/book-cost per snapshot
GET    /api/instruments                     # latest-snapshot instruments
GET    /api/instruments/{id}/history        # all snapshots for one instrument
GET    /api/instruments/{id}/orders         # matched orders
GET    /api/groups                          # CRUD + PUT /{id}/members
GET    /api/health
```

---

## Persistence & determinism

- Snapshot files are content-hashed, so re-uploading the same file is rejected (use `force` to override).
- Orders are de-duped by `order_fingerprint`, which makes re-importing a longer order history safe and idempotent.
- `init_db()` runs `Base.metadata.create_all` plus a small inline migration that backfills `order_fingerprint` and drops dupes. There is **no Alembic** yet — see Improvements.

---

## Roadmap / known gaps

See the issues / next-steps document distilled from a code review:

1. Surface the snapshot diff (currently stored in `import_batches.diff_summary` but never shown).
2. Snapshot-vs-snapshot comparison view (pick two dates, list deltas per instrument).
3. Concentration & allocation risk on the Overview (largest holdings as % of portfolio, drift vs. group targets).
4. Live price refresh between Barclays exports (yfinance/Stooq via ISIN/SEDOL).
5. Per-position **time-weighted return** (Modified Dietz) using order cashflows — more accurate than the current `CAGR(net_cost → current_value)`.
6. Benchmark overlay (FTSE 100 / S&P 500 / VWRL) on the historical-estimate chart.
7. Drawdown per holding (peak-to-current) plus a "down N% from peak" filter.
8. UK CGT view: realised gains by tax year, with section 104 / same-day / 30-day matching.
9. Push aggregations into SQL (`portfolio_value_timeseries` currently does N round-trips).
10. Add Alembic migrations and pytest coverage for parsers + analytics.
