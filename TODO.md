# High Priority Improvements

## 1. Add Alembic migrations

- [ ] **File:** `backend/alembic/` (new)
- [ ] **Problem:** The project uses `Base.metadata.create_all` + inline SQL migrations in `database.py`. This approach is fragile — it won't handle schema drops, column type changes, or work reliably when multiple instances share the DB. Schema changes are undocumented and ad-hoc.
- [x] **Fix:**
  1. `pip install alembic` and add to `requirements.txt`
  2. `alembic init backend/alembic`
  3. Configure `alembic.ini` with the async SQLite URL
  4. Set `alembic.env.py` to use the existing SQLAlchemy engine and `Base.metadata`
  5. Generate initial migration: `alembic revision --autogenerate -m "initial schema"`
  6. Convert inline migrations in `database.py` (`_migrate_order_dedupe`, `_migrate_match_metadata`, `_migrate_portfolio_metadata`) into proper Alembic upgrade/downgrade functions
  7. Replace `init_db()` calls to `alembic command upgrade head`
  8. Ensure `alembic/versions/` is tracked in git

---

## 2. Add Python linting and type checking

- [x] **File:** `backend/.ruff.toml` (new)
- [x] **Problem:** No linter or type checker configured. `order_service.py` is 865 lines with no type safety guarantees. Code quality will drift and bugs will go undetected until runtime.
- [x] **Fix:**
  1. Add `ruff>=0.8.0` and `mypy>=1.11.0` to `requirements.txt` (dev deps)
  2. Create `backend/.ruff.toml` with sensible defaults (E/W/F/pycodestyle/pylint rules, line length 100)
  3. Add `mypy.ini` or pyproject.toml section with strict settings (disallow untyped defs, disallow any generics, etc.)
  4. Run `ruff check backend/ --fix` and `ruff format backend/`
  5. Run `mypy backend/` and fix type errors (focus on service layer first)
  6. Add scripts to `requirements.txt` or a `Makefile`: `"lint": "ruff check backend/ && ruff format --check backend/"`, `"typecheck": "mypy backend/"`

---

## 3. Add `.env.example` file

- [x] **File:** `.env.example` (new, in repo root)
- [ ] **Problem:** The config uses `PORTFOLIO_DATABASE_URL` env var but there's no `.env.example` documenting what's available. This makes onboarding, deployment, and local configuration guesswork.
- [ ] **Fix:**
  1. Create `.env.example` with all `PORTFOLIO_*` env vars documented:
     ```
     # Database URL (defaults to sqlite+aiosqlite:///./portfolio.db)
     PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///./portfolio.db

     # (Add any other settings as they are added to config.py)
     ```
  2. Add `.env` to `.gitignore` (it should never be committed)
  3. Update README.md to reference `.env.example` in the Quick Start section

---

## 4. Fix CGT frontend integration

- [ ] **File:** `frontend/src/layout/Sidebar.tsx`, `frontend/src/routes/CGT.tsx`
- [ ] **Problem:** The CGT service (`cgt_service.py`, 444 lines), router (`cgt.py`), and frontend types (`CGTSummaryResponse`, `CGTTaxYearSummary`, etc.) are all built, but the CGT route doesn't appear to be linked from the sidebar navigation. Users can't access the UK Capital Gains Tax view that's been implemented.
- [ ] **Fix:**
  1. Review `Sidebar.tsx` — add a "CGT" nav item linking to the `/cgt` route
  2. Review `CGT.tsx` — verify it uses the `api.getCgtSummary()` call and renders tax year summaries, instrument summaries, and gain/loss breakdowns
  3. If `CGT.tsx` is empty or stubbed out, implement the view using the existing types and API:
     - Tax year summary table (proceeds, cost, gain, loss per year)
     - Per-instrument breakdown with section 104 pool status
     - Same-day / 30-day / pool matching detail
  4. Add the route to `App.tsx` if not already registered
  5. Add a test or manual verification that the CGT endpoint returns valid data
