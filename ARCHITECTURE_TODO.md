# Architecture TODO

Priority-ordered remediation plan for the issues surfaced in the code review.
Phases are sequenced so that earlier work unlocks later work — in particular,
**Phase 1 must land before any of the structural refactors** because it
provides the safety net (tests, lint, types, CI) needed to make the rest safe.

Each item lists the problem, the concrete change, the files involved, and how
we'll know it's done.

---

## Phase 1 — Safety net (do this first)

> Goal: every later change has a test, a type-checker, and a CI run protecting
> it. Keep behaviour identical; just add scaffolding.
>
> Status: complete.

### 1.1 Add `pyproject.toml` and adopt `ruff` + `mypy`

- **Why:** there is no packaging manifest, and `pytest.ini` uses
  `pythonpath = backend` as a workaround. No linter/type-checker is
  configured, so the next refactor lands on un-checked code.
- **Change:**
  - Create `pyproject.toml` at the repo root declaring the `backend` package
    (`[tool.setuptools.packages.find] where = ["backend"]`), Python `>=3.12`,
    and runtime deps moved from `requirements.txt`.
  - Add `[tool.ruff]` (line length 100, rules: `E,F,I,UP,B,SIM,RUF`) and
    `[tool.mypy]` (`strict = true`, `disallow_any_generics = true`,
    plugins for SQLAlchemy + Pydantic).
  - Move pytest config into `[tool.pytest.ini_options]`; delete `pytest.ini`.
  - `pip install -e .[dev]` should be the one-liner setup.
- **Done when:** `ruff check`, `ruff format --check`, and `mypy backend/app`
  all pass on `main` with zero suppressions.

### 1.2 Test infrastructure

- **Why:** integration tests use `asyncio.run()` because there is no
  `pytest-asyncio`, no `conftest.py`, and the engine is bound at import time.
  Adding fixtures now means every later refactor can ship with tests.
- **Change:**
  - Add `pytest-asyncio` (mode `auto`) and `httpx` to dev deps.
  - Create `backend/tests/conftest.py` with:
    - `async_engine` fixture (function-scoped, `sqlite+aiosqlite:///:memory:`,
      `Base.metadata.create_all`).
    - `async_session` fixture yielding a `AsyncSession` bound to the engine.
    - `client` fixture wiring `app.dependency_overrides[get_session]` to that
      session and returning an `httpx.AsyncClient(app=app, base_url=…)`.
    - Sample-file fixtures: tiny redacted `.xls` / `.csv` files committed
      under `backend/tests/fixtures/` so parser tests are deterministic.
  - Rewrite `test_import_service.py` to use the fixtures (drop
    `asyncio.run`).
- **Done when:** all existing tests pass through fixtures and at least one
  new HTTP-level test exercises `POST /api/imports`.

### 1.3 Frontend lint + typecheck

- **Why:** no `eslint`, no `tsc --noEmit` in CI, no test runner.
- **Change:**
  - Add `eslint` (typescript-eslint, react-hooks, react-refresh) and
    `prettier` config; one `npm run lint`/`npm run typecheck` script each.
  - Add `vitest` + `@testing-library/react`; one smoke test that mounts
    `App` against a mocked `api`.
- **Done when:** `npm run lint`, `npm run typecheck`, `npm test` all pass.

### 1.4 CI

- **Why:** without CI the rest of this list is a wishlist.
- **Change:** add `.github/workflows/ci.yml` running, on every PR:
  `ruff check && mypy && pytest && (cd frontend && npm ci && npm run lint &&
  npm run typecheck && npm test && npm run build)`.
- **Done when:** CI is green and required.

---

## Phase 2 — Configuration & DB plumbing

### 2.1 Stop binding the engine at import time

- **Why:** `engine = create_async_engine(...)` runs in `app/database.py` at
  module load, using a path computed from `__file__`. Tests have to bypass
  it; cwd-dependent edge cases produced the empty `backend/portfolio.db`.
- **Change:**
  - Replace the module-level `engine` / `SessionLocal` with
    `get_engine(settings: Settings) -> AsyncEngine` and
    `get_sessionmaker(engine) -> async_sessionmaker[AsyncSession]`,
    cached on the FastAPI app state via `lifespan`.
  - `get_session` becomes `request.app.state.sessionmaker()`.
  - `import_cli.py` builds its own engine from the same factory.
- **Done when:** no module-level DB state exists; tests inject a fixture
  engine via `app.dependency_overrides`.

### 2.2 Move the SQLite file under `data/` and consolidate paths

- **Why:** there are two `portfolio.db` files in the repo (`backend/`
  empty, repo root live). The `data/` directory is already gitignored as a
  whole.
- **Change:**
  - Default `database_url` to `sqlite+aiosqlite:///${project_root}/data/portfolio.db`.
  - Delete `backend/portfolio.db` (empty).
  - Document `PORTFOLIO_DATABASE_URL` in a new `.env.example`.
- **Done when:** only one `portfolio.db` exists and it's under `data/`.

### 2.3 Enable SQLite foreign keys

- **Why:** `ondelete="CASCADE"`/`SET NULL` in `models.py` are silently no-ops
  because SQLite ships with FKs off. Cascades currently work only because
  SQLAlchemy ORM does the deletes.
- **Change:** add a `connect` event listener on the sync DBAPI connection
  that runs `PRAGMA foreign_keys=ON;`. Add a regression test that issues a
  raw `DELETE` and verifies cascade behaviour.
- **Done when:** the test passes.

### 2.4 Adopt Alembic

- **Why:** `database.py` has hand-rolled SQLite-only migrations
  (`_migrate_order_dedupe`, `_migrate_portfolio_metadata`) baked into
  `init_db()`. Rollback is impossible; every boot re-runs them.
- **Change:**
  - Add `alembic` dependency; `alembic init backend/migrations`.
  - Generate a baseline revision from current `Base.metadata` and a follow-up
    revision that mirrors the two `_migrate_*` functions (so existing dbs
    upgrade cleanly).
  - Remove the migration calls from `init_db`; `init_db` only runs
    `create_all` for tests / brand-new databases.
  - `start_backend.sh` runs `alembic upgrade head` before uvicorn.
- **Done when:** `alembic upgrade head` brings any prior db forward and the
  inline migration code is gone.

---

## Phase 3 — Core domain correctness

### 3.1 Define a single source of truth for DRIP

- **Why:** `Order.is_drip` is stored at import time using one threshold while
  every analytics endpoint recomputes `is_drip` from a query-param threshold.
  The two answers can disagree silently.
- **Decision (proposed):** treat DRIP as derived. Drop the
  `Order.is_drip` column. Compute it in a single helper
  (`is_drip(order, threshold)`) and use it everywhere.
- **Change:**
  - Alembic migration: drop `orders.is_drip`.
  - Replace every read of `order.is_drip` with the helper.
  - Move the threshold from a query param on each request to a row in a new
    `user_preferences` table (single-row), surfaced through one
    `/api/preferences` endpoint. Frontend stops sending it on every call.
  - Update `order_fingerprint` callers — `is_drip` was never in the
    fingerprint, so no fingerprint change is needed.
- **Done when:** there is exactly one definition of "is this order a DRIP",
  and changing the threshold updates every analytics view consistently.

### 3.2 Make "current snapshot" date-aware, not id-aware

- **Why:** `get_current_snapshots` and `get_latest_batch_for_account` use
  `MAX(import_batch_id)`. `--force` re-imports of older files and out-of-
  order multi-account uploads break that monotonic assumption. Worse,
  `portfolio_value_timeseries` reads `diff_summary["closed"]` (a JSON blob
  written at ingest) to decide which instruments to drop — coupling two
  pieces of state that can disagree.
- **Change:**
  - Sort by `(ImportBatch.as_of_date DESC, ImportBatch.id DESC)` everywhere
    "latest" is queried.
  - Reconstruct closures at query time as "instrument has no snapshot in the
    latest batch for its account" rather than reading `diff_summary`.
  - Keep `diff_summary` as a UI-display artefact only; never depend on it
    for analytics.
- **Done when:** unit tests cover (a) `--force` re-import of an older snapshot
  not changing "current", (b) cross-account imports preserving each
  account's latest, (c) `portfolio_value_timeseries` matching a hand-computed
  result on a fixture with closures.

### 3.3 Normalise broker output at the parser boundary

- **Why:** `barclays_order_parser` stores raw cell values; `hl_parser` stores
  `abs(value)`. `_cashflow_amount` negates sells, but
  `get_order_analytics` adds `cost_proceeds_gbp` raw. A future broker emitting
  negative sells would silently flip totals.
- **Change:**
  - Document on `ParsedOrderRow` that `cost_proceeds_gbp` is **always
    positive** and represents money-out for buys, money-in for sells.
  - Assert `cost_proceeds_gbp >= 0` in each parser.
  - Audit `_cashflow_amount`, `get_order_analytics`, `get_cashflow_timeseries`
    against that contract; add a fixture-driven test per broker.
- **Done when:** swapping in a parser that emitted signed values would fail
  loudly, not silently.

### 3.4 Fix the Stooq FX assumption

- **Why:** `market_data_service.fetch_latest_quote` hardcodes
  `price_ccy: "GBP"` regardless of symbol — `spx.us` is stored as sterling.
- **Change:**
  - Have `_fetch_stooq_csv` return raw close + symbol; let
    `fetch_latest_quote` infer currency from the symbol suffix
    (`.us` → USD, `.uk` → GBP/GBX, etc.) and store both `price` and
    `price_ccy`. FX conversion to GBP is the caller's job.
  - Add a `quote_history` table if/when we need a series; the current
    `instrument_quotes` row stays as a "latest" cache.
- **Done when:** quotes for a US ticker no longer come back as GBP.

---

## Phase 4 — Performance & DTO hygiene

### 4.1 Push aggregations into SQL

- **Why:** the Overview page hits `select(Order)` 4–6 times per render and
  walks the table in Python each time. `_all_group_totals`,
  `_single_group_summary`, `portfolio_value_timeseries`, and
  `get_estimated_portfolio_timeseries` all do "load everything, aggregate in
  dicts."
- **Change:**
  - Replace `_all_group_totals` and `_single_group_summary` with one
    `SELECT m.group_id, SUM(s.value_gbp) ... GROUP BY m.group_id`.
  - Compute `portfolio_value_timeseries` with a window-function or a
    correlated subquery picking the latest per-instrument-per-account
    snapshot at-or-before each batch date.
  - Introduce a `PortfolioContext` dataclass loaded once per request
    (current snapshots, instrument metadata, group memberships, orders) and
    pass it into the analytics helpers; stop re-fetching inside services.
- **Done when:** Overview page makes O(1) queries per analytics block, not
  O(N).

### 4.2 Remove the duplicated `_trailing_drip_yield_pct` call

- `get_order_positions` lines 524–542 compute the value twice per row to gate
  the `if … is not None` rounding. Compute once, round once.

### 4.3 Split `InstrumentOut`

- **Why:** 23 fields covering metadata + latest snapshot + quote + peak +
  group memberships + drift. Every consumer pays the wire cost; new fields
  are awkward to add.
- **Change:** introduce `InstrumentListItem` (Holdings table) and
  `InstrumentDetail` (instrument detail page). Holdings drops the quote,
  peak/drawdown, and trailing yield fields it doesn't render.
- **Done when:** `InstrumentOut` is gone or only used as a server-internal
  type, and the wire payload for `/api/instruments` is materially smaller.

### 4.4 Decide on instrument "current price"

- `latest_value_gbp / quantity` and `latest_quote_price_gbp` are two answers.
  Pick the snapshot value as canonical for portfolio math; expose the quote
  separately as "live mark" with its own UI affordance.

---

## Phase 5 — Frontend coherence

### 5.1 Push `account_filter` to the backend

- **Why:** `Overview.tsx` reimplements `build_portfolio_summary` in JS for
  the filtered case while charts remain whole-portfolio. Two definitions of
  allocation/best/worst that can drift.
- **Change:**
  - `GET /api/portfolio/summary?account=…`,
    `GET /api/portfolio/timeseries?account=…`,
    `GET /api/orders/cashflow-timeseries?account=…`,
    `GET /api/orders/estimated-timeseries?account=…`.
  - React Query keys include `accountFilter`.
  - Delete the JS `summary` recomputation in `Overview.tsx`.
- **Done when:** switching account filter updates KPIs and charts together,
  with no client-side aggregation logic.

### 5.2 Error boundary + visible error states

- Add a top-level `<ErrorBoundary>` and a small `<QueryError>` component;
  every `useQuery` callsite renders `error` alongside `isLoading`.

### 5.3 Replace `window.location.href` navigation

- `WhatChangedCard` does a full reload via `window.location.href` and drops
  the React Query cache. Use `navigate()`.

### 5.4 Configurable API base

- `requestJson` is hardcoded to `/api/...`. Read
  `import.meta.env.VITE_API_BASE_URL ?? ""` and prefix; default keeps the
  Vite proxy behaviour.

### 5.5 Audit `lucide-react@^1.7.0`

- The current upstream major is `0.4xx`; `1.7.0` looks like an unrelated
  fork. Pin to the real `lucide-react` (or `@lucide/react` if migrating)
  and verify icon imports.

### 5.6 Trim component sizes

- `Overview.tsx` (561), `GroupsSection.tsx` (666),
  `GroupPerformancePanel.tsx` (699), `ChartPanel.tsx` (419) all mix layout,
  data-shaping, and mutations. Extract data-shaping into hooks
  (`useOverviewMetrics`, `useGroupPerformance`) and split visual sub-trees
  into co-located components.

---

## Phase 6 — Operational polish

### 6.1 Stop leaking exception messages to the API

- `routers/imports.py:55,95` and `routers/orders.py:60,97` do
  `raise HTTPException(400, f"Import failed: {exc}")`. Log the exception
  with traceback (via `logging.getLogger(__name__).exception(...)`) and
  return a stable, sanitised message.

### 6.2 Structured logging

- Configure `logging.config.dictConfig` once on startup (JSON in prod,
  pretty in dev). Replace `print()` in `import_cli.py`. Log import outcomes
  (batch id, row count, dedup count, duration).

### 6.3 Validate request inputs

- `drip_threshold: float = Form(default=1000.0)` accepts negative, zero,
  NaN, infinity. Use `Annotated[float, Query(ge=0, le=1_000_000)]` (or
  similar) on every endpoint that takes it.
- Same for `limit` query params.

### 6.4 Tighten CORS for non-dev

- `allow_origins=["*"]` is fine for local dev but should be driven by an
  env-configured allowlist before any non-localhost deployment.

### 6.5 Patch `infer_asset_class` ordering

- `PATCH /api/instruments/{id}/market` runs `infer_asset_class` after the
  user has explicitly cleared `asset_class`, which silently re-fills it.
  Only infer when the field was never set, not when it was explicitly
  cleared.

### 6.6 Document the SQLite single-writer constraint

- Running `import_cli` while uvicorn is up will work for reads but writes
  will serialise. README should call this out, or move imports through the
  HTTP API only.

### 6.7 Commit redacted broker fixtures

- Add small `barclays-portfolio.xls`, `barclays-orders.xls`,
  `hl-holdings.csv`, `hl-activity.csv` under `backend/tests/fixtures/`
  with synthetic data. Parsers gain real regression coverage.

---

## Out of scope here (tracked in README roadmap)

The README already lists feature work (snapshot diff UI, comparison view,
concentration risk, live price refresh, time-weighted return, benchmarks,
drawdowns, UK CGT, etc). Those are intentionally **not** in this document;
this document is about the foundation those features will be built on.

Once Phase 1–3 are done, the README roadmap items become small, isolated
changes instead of cross-cutting refactors.

---

## Quick-reference checklist

- [x] **1.1** `pyproject.toml`, `ruff`, `mypy`
- [x] **1.2** `pytest-asyncio`, `conftest.py`, fixture files
- [x] **1.3** Frontend `eslint`, `prettier`, `vitest`
- [x] **1.4** GitHub Actions CI
- [ ] **2.1** Engine factory, no module-level DB state
- [ ] **2.2** DB under `data/`, delete empty `backend/portfolio.db`
- [ ] **2.3** `PRAGMA foreign_keys=ON`
- [ ] **2.4** Alembic baseline + retire inline migrations
- [ ] **3.1** Single DRIP definition (derived)
- [ ] **3.2** Date-aware "current snapshot"
- [ ] **3.3** Normalised parser contract for `cost_proceeds_gbp`
- [ ] **3.4** Stooq currency inference
- [ ] **4.1** SQL aggregations replace Python loops
- [ ] **4.2** Single-call `_trailing_drip_yield_pct`
- [ ] **4.3** Split `InstrumentOut` into list/detail DTOs
- [ ] **4.4** One canonical "current price"
- [ ] **5.1** `account_filter` server-side
- [ ] **5.2** Error boundary + per-query error UI
- [ ] **5.3** `navigate()` everywhere
- [ ] **5.4** `VITE_API_BASE_URL`
- [ ] **5.5** Audit `lucide-react` version
- [ ] **5.6** Decompose oversized components
- [ ] **6.1** Sanitise import error responses
- [ ] **6.2** Structured logging
- [ ] **6.3** Input validation on numeric query/form params
- [ ] **6.4** Env-driven CORS allowlist
- [ ] **6.5** `infer_asset_class` only on unset
- [ ] **6.6** Document single-writer constraint
- [ ] **6.7** Commit broker fixtures
