# Automated Account Sync Implementation Plan

> **For Hermes:** Parent implements in-session (subagents hard-stop ~600s); use subagents only for read-only review. Follow `broker-data-integrations` and `test-driven-development`.

**Goal:** One command (and later a daily timer) that refreshes every account — Trading 212 via API, HL and Barclays via scripted browser downloads — and imports the results correctly with no manual navigation or file picking.

**Architecture:** Three layers with hard boundaries.
1. **Fetchers** (Playwright, persistent browser profile) log in with `.env` credentials and save raw exports into an inbox. They never touch the database.
2. **Classifier + sync-all** detects each file's type from its *content* (never its filename), validates it, and routes it to the existing importers; then runs the Trading 212 API sync. This is the only layer that writes.
3. **LLM repair (Bedrock)** runs only when a scripted step fails: it proposes a new selector/route under a constrained action policy, and the run still stops for review. Normal runs make zero LLM calls.

**Tech Stack:** Python 3.14 (.venv), Playwright (already installed, chromium-1217), python-calamine (already used by Barclays parsers), FastAPI, SQLite, pytest; boto3 (new, Phase 4 only).

---

## Evidence gathered (2026-09-22, read-only)

`~/Downloads` holds 36 broker exports. Contents were inspected with digits masked; no values recorded.

| Export | Filename pattern | Content signature | Importer |
|---|---|---|---|
| HL holdings | `account-summary (N).csv` | line 1 `HL Fund & Share Account`; `Spreadsheet created at` date | `import_hl_holdings_csv` |
| HL activity | `portfolio-summary (N).csv` | line 1 `Portfolio Summary`; header `Trade date,Settle date,Reference,…`; `Valuation as at` | `import_hl_orders_csv` |
| Barclays holdings | `LoadDocstore (N).xls` (~14 KB) | sheet = account, row 2 has `Identifier`, `Quantity Held` | `import_barclays_xls` |
| Barclays orders | `LoadDocstore (N).xls` (~64 KB) | row 2 has `Date`, `Order Status`, `Buy/Sell` | `import_order_history` |
| Trading 212 | API | — | existing `/trading212/sync` |

Findings that shape the plan:
- **Filenames are ambiguous and have already caused misroutes:** one HL activity file was imported as a *holdings snapshot* (batch 32 `portfolio-summary.csv`), and several `account-summary` files went through the orders importer returning 0 rows. Content classification fixes this.
- **Barclays uses the same filename for two different exports**; only content distinguishes them.
- **Backlog:** 6 exports were never imported (latest HL holdings ×2, HL activity ×1, Barclays holdings ×2, Barclays orders ×1, dated 20–21 Sep).
- Barclays holdings files carry no date; the snapshot date must come from download time (fetcher) or file mtime (backlog).
- `data/auto_downloaded/` exists (git-ignored, empty) — reuse it as the inbox.
- Stock-level `xlrd` fails on these files (`CompDocError`); calamine reads them — keep calamine.
- Batch 32 needs a separate data-quality review (possibly delete and re-import as activity). **Not** in scope for automation; flag to user.

## Credentials (`.env`, git-ignored)

```
PORTFOLIO_HL_USERNAME=
PORTFOLIO_HL_DATE_OF_BIRTH=        # DDMMYY as HL asks
PORTFOLIO_HL_PASSWORD=
PORTFOLIO_HL_SECURE_NUMBER=        # 6 digits; fetcher enters only the requested positions
PORTFOLIO_BARCLAYS_SURNAME=
PORTFOLIO_BARCLAYS_MEMBERSHIP_NUMBER=
PORTFOLIO_BARCLAYS_PASSCODE=
PORTFOLIO_BARCLAYS_MEMORABLE_WORD= # fetcher enters only the requested letters
PORTFOLIO_SYNC_INBOX=data/auto_downloaded
PORTFOLIO_BROWSER_PROFILE=~/.local/share/stocks-browser
PORTFOLIO_SYNC_NOTIFY=whatsapp     # optional: MFA prompts + run summary
```

Exact field names confirmed during Phase 0 recording. Only names are added to `.env.example`. Code must never log values, and screenshots/traces kept on failure must redact the login steps (disable tracing until post-login).

## Where automation stops

| Step | Automated? |
|---|---|
| Navigation, export clicks, download, validation, import | Yes, fully |
| Password, secure-number digits, memorable-word letters | Yes, from `.env` |
| SMS/call-back MFA (HL), PINsentry/app approval (Barclays) | **No.** Minimised with a persistent "trusted device" profile. When triggered, the run pauses, sends a notification, and waits for the code to be typed into a local prompt (bounded, e.g. 5 min, then exit cleanly) |
| Fully unattended timer runs | Only while the profile's device trust holds; otherwise the run degrades to "HL needs a code" and still does Trading 212 plus whatever succeeded |

Action policy for all fetchers, scripted or LLM: allowed hosts `*.hl.co.uk`, `*.barclays.co.uk`, `*.smartinvestor.barclays.co.uk`. No click on elements whose accessible name matches `/deal|buy|sell|trade|transfer|withdraw|confirm order|place order/i`, except the explicitly whitelisted export controls. It's cheap insurance, not a claim that trading is easy.

---

## Phase 0 — Record the routes (with Geoff, ~20 min, read-only)

### Task 0.1: Headed recording session
- Run `.venv/bin/playwright codegen --save-storage=... https://online.hl.co.uk/` in a persistent profile; Geoff logs in manually; record clicks to (a) account summary → download CSV, (b) portfolio summary/activity → download CSV, for **every** HL account (confirm whether ISA/SIPP exist beyond Fund & Share).
- Repeat for Barclays Smart Investor: holdings export and order-history export, with any date-range controls.
- Output: `automation/routes/hl.md`, `automation/routes/barclays.md` with URL, role and accessible name of each control (prefer `get_by_role` over CSS), and the login field sequence including partial-digit prompts.
- Decide the activity date-range setting (widest available; duplicates are deduped by fingerprint).

## Phase 1 — Content classifier + inbox sync-all (no browser)

### Task 1.1: Classifier module
- Create `backend/app/services/export_classifier.py`: `classify_export(filename, data) -> ExportKind` with `HL_HOLDINGS | HL_ACTIVITY | BARCLAYS_HOLDINGS | BARCLAYS_ORDERS | UNKNOWN`, using the signatures above (CSV first line + header row; XLS header row via calamine). Also reject HTML/login pages saved as `.csv`/`.xls` (magic bytes / `<html`).
- Test first: `backend/tests/test_export_classifier.py`, using **synthetic** fixtures that mirror the structure (no real data in git). Cover each kind, the swapped-filename case (`account-summary.csv` that is really activity), HTML error page, empty file, and unknown workbook.

### Task 1.2: Sync-all service
- Create `backend/app/services/sync_all_service.py`: `sync_inbox(session, inbox, *, now) -> SyncReport`.
  - Classify every file; UNKNOWN goes to `inbox/rejected/` with a reason.
  - Import **in chronological order per kind** (snapshot "closed" semantics depend on order); dates come from file metadata (HL `Spreadsheet created at` / `Valuation as at`), otherwise file mtime.
  - `DuplicateImportError` → `unchanged`, not a failure.
  - Move processed files to `inbox/processed/YYYY-MM-DD/` only after commit; a failure leaves the file in place.
  - Then call the existing Trading 212 combined sync; its failure is reported per account, not fatal to the others.
- Tests: in-memory DB covering order, duplicates→unchanged, rejected unknown, partial failure isolation, and idempotent re-run.

### Task 1.3: CLI + API + button
- `backend/app/sync_cli.py` → `make sync` (`--inbox`, `--include-downloads` for backlog, `--dry-run` classify-only).
- `POST /sync/all` guarded by the existing `require_local_origin`; the ImportPanel gets a **Sync all accounts** button with a per-account report.
- `--include-downloads --dry-run` against `~/Downloads` must list exactly the 6 never-imported files as new (checked on a **copy** of `portfolio.db`).

### Task 1.4: Freshness indicator
- `GET /sync/status`: per account, last snapshot date, last order import and age; Dashboard/Import show a stale badge (>7 days, configurable).

## Phase 2 — Scripted fetchers

### Task 2.1: Fetcher framework
- `automation/fetch/base.py`: persistent Playwright context (`PORTFOLIO_BROWSER_PROFILE`), host allowlist enforced via `page.route`, click-guard wrapper enforcing the deny regex, `expect_download` helper that saves to the inbox with a `<broker>-<kind>-<timestamp>` name, and structured step results (`ok | needs_mfa | selector_failed | validation_failed`).
- Each download is validated immediately with `classify_export` against the expected kind and today's date (HL metadata) before the step counts as success.
- Tests: guard/allowlist unit tests and a local fake-broker HTML fixture served by a pytest HTTP server (login → export → download), including an injected "Buy" button that must be refused.

### Task 2.2: HL fetcher
- `automation/fetch/hl.py`: login (username, DOB, password, requested secure-number positions parsed from the page labels), MFA detect → pause/notify → local code prompt, then downloads per Phase 0 routes for each account.
- Session reuse: skip login if the profile is still authenticated.

### Task 2.3: Barclays fetcher
- `automation/fetch/barclays.py`: same pattern; passcode plus requested memorable-word letters; both exports; PINsentry/app approval handled as `needs_mfa`.

### Task 2.4: One command
- `make sync-all` = run fetchers (HL, Barclays, in parallel, separate pages) → `sync_inbox` → Trading 212 → print/notify the per-account report. Exit non-zero only if **nothing** refreshed.
- Live verification: one real run against a **copy** of the database first; compare the report with a manual check; then run against the working DB with a verified backup (`sqlite3 .backup`).

## Phase 3 — Scheduling and notifications

### Task 3.1: systemd user timer
- `~/.config/systemd/user/stocks-sync.{service,timer}`, daily ~18:30 on weekdays (after UK close), running `make sync-all --non-interactive`. In non-interactive mode MFA → skip that broker and notify "HL needs you: run `make sync-all`".
- Bounded: whole-run timeout of 10 min; each fetcher 3 min.

### Task 3.2: Notifications
- Summary via the Hermes WhatsApp home channel (or `notify-send` fallback): refreshed/unchanged/failed per account, with no values.

## Phase 4 — LLM-assisted repair (Bedrock), only after Phase 2 is stable

### Task 4.1: Repair agent
- Triggered only on `selector_failed`. Input: the accessibility tree plus a screenshot of the **post-login** page (tracing is disabled during login, and credential fields are never sent), the goal ("download account summary CSV") and the last known route.
- Model: Bedrock (data stays in the AWS account). Output: a JSON action (`click role+name`, `goto allowed-url`), executed through the same guard, with a budget of 8 actions.
- On success: the file is downloaded and validated as normal, **and** a proposed diff to `automation/routes/*.md` / fetcher selectors is written to `automation/repairs/`. The scripted route is not updated automatically; Geoff (or a Hermes session) reviews and commits it.
- Tests: fake-broker fixture with renamed buttons → repair finds the new control; a fixture where the only matching button is "Buy" → the repair refuses and reports.

## Completion gate
- Classifier, sync-all, guard and fake-broker tests; existing backend/frontend tests, lint (`make check`) and build all pass, with pre-existing failures listed separately.
- Backlog dry-run matches the 6 known files; live run on a DB copy is correct; working-DB run has a verified backup.
- `.env` absent from the index; staged-patch secret scan clean; independent review of tracked **and untracked** files; push and confirm the local and remote commit IDs match.

## Decisions (Geoff, 2026-09-22)
1. HL: a single account (Fund & Share). No ISA/SIPP.
2. Barclays: a 5-digit passcode plus requested memorable-word characters when "remember me" holds. Without it, the membership number and PIN are also needed. Fetcher: tick "remember me" and handle both paths. `.env` adds `PORTFOLIO_BARCLAYS_PIN`.
3. HL: a password plus 3 of the 6 secure-number digits; no SMS MFA observed. HL is expected to be fully unattended.
4. Timer about 18:30 on weekdays, WhatsApp summary: approved.
5. Batch 32: **done, 2026-09-22.** It was an empty snapshot batch (0 holdings rows, file hash = order batch 17, which already imported that file's trades correctly). Removed after a verified backup (`~/.local/share/stocks-db-backups/portfolio-20260922-234402-before-batch32.db`). Rehearsed on a copy first: across 37 API endpoints, the only changes were the batch list and the removal of a duplicate 2026-09-02 point from group-performance timeseries. The live result is byte-identical to the rehearsal.

## Status (2026-09-23)

**Built and verified**
- Content classifier (`export_classifier.py`): identifies all 34 real historical exports correctly.
- Inbox sync-all (`sync_all_service.py`, `sync_runner.py`, `sync_cli.py`, `POST /api/sync/all`, `GET /api/sync/status`, *Sync all accounts* panel with per-account freshness).
- HL fetcher: fully automatic login (username + DOB → password + 3 requested Secure Number digits, read from each box's label). Downloads `account_summary_csv` and the capital-account activity CSV (custom 90-day window; row fingerprints dedupe overlaps). No MFA observed.
- Backlog: 6 never-imported exports and 2 fresh HL downloads imported into the working DB after a verified backup and a byte-for-byte rehearsal on a copy (only import timestamps differed).
- Pre-existing bug fixed: naive/aware datetime comparison in `matching/candidates.py` and `scoring.py` crashed HL snapshot import after same-session order imports.
- Weekday 18:30 Hermes cron job `7bd81be10e76` (`~/.hermes/scripts/stocks_sync.sh`, WhatsApp), created **paused**.

**Blocked: Barclays**
- The route is mapped: remembered surname/membership → Continue → "Passcode and memorable word" tab → `#passcode` + `memorableCharacters-input-N` (positions read from labels) → `#submitAuthentication`.
- One automated submit returned "There's a Problem". Automatic login is paused by `~/.local/share/stocks-browser/barclays-login-blocked` so repeated attempts cannot lock the account.
- Unconfirmed cause: credential mismatch (PIN and passcode in `.env` are identical), a character-position/case issue, or headless/bot detection.
- The export navigation after login is still unmapped.

**Review items**
- 3 new orders need matching review: 2 Barclays buys matched cross-account (`auto_review`), 1 HL sale unmatched (instrument `BCHS` closed, and the name has a `*1` suffix).

## Status (2026-09-23 00:45) - deployed on the Surface

**Live on the Surface (production, https://solarpi.hopto.org:5000)**
- The Surface production database (`/var/lib/stocks/portfolio.db`) is the master. This PC's `portfolio.db` is a stale working copy.
- Release: `/opt/stocks/current` → `releases/stocks-upgrade.3w7KTcNz` (commit 4584a45). Rollback target: `releases/stocks-install.kOvgvno0`.
- `stocks-sync.timer`: Mon-Fri 18:30 Europe/London → `stocks-sync.service` (`User=stocks`, same systemd sandbox as the web app, bounded to 15 min, each fetcher 5 min).
- Broker logins read `/etc/stocks/brokers.env` (root 0600, HL only). The web service never loads it.
- The public web app cannot trigger a sync (`POST /api/sync/all` → 403 in public mode). The Import tab shows per-account freshness and the last run only.
- Hermes cron `b29835e1f4e9` on the Surface: 18:45 weekdays, sends the WhatsApp summary from the journal. No agent or LLM runs.
- Chromium headless shell: `/opt/stocks/playwright`, using the ubuntu24.04 fallback build because Playwright doesn't support 26.04 yet.
- Verified twice by running the unit by hand: HL ok, Trading 212 ok, Barclays skipped (not configured), DB integrity ok.

**Lockout safety**
- HL or Barclays rejecting a login writes `/var/lib/stocks/browser/{hl,barclays}-login-blocked`, and no further attempts are made until it is deleted (`sudo -u stocks rm ...`).

**Deploy procedure**
- `bash deploy/upgrade-surface.sh --prepare-only` (as geoff, no sudo) then `--upgrade`.
- It snapshots the DB into `/var/backups/stocks/`, switches the release, health-checks, and rolls back automatically if the check fails.

**Open**
- Barclays: the account is locked. The user must restore access with Barclays, then add `PORTFOLIO_BARCLAYS_*` to `/etc/stocks/brokers.env`. The first run should be one attempt with `--headed` on this PC. The export route after login is not yet mapped.
- Review 2 unmatched orders (Data → Matching) in production.
- Pre-existing lint (30) and mypy (23) debt is unchanged.
- `install-surface.sh --check` tests fail on the Surface once installed, by design (they refuse an existing install). Run them on a fresh VM or skip them there.

## Next session checklist (left open 2026-09-23 ~00:50)
1. **Verify the first unattended run:** the 18:30 `stocks-sync.timer` run and the 18:45 WhatsApp summary (Surface Hermes cron `b29835e1f4e9`). On the Surface, check `journalctl -u stocks-sync --since today`, and check the Import tab freshness on the live site.
2. **Barclays** (blocked; the account is locked after one automated attempt plus the user's own attempts):
   - The user restores access with Barclays.
   - Check the `PORTFOLIO_BARCLAYS_*` values. PIN and passcode were identical in `.env`, which is suspicious.
   - Add them to `/etc/stocks/brokers.env` on the Surface.
   - Delete any `barclays-login-blocked` marker.
   - Make ONE `--headed` attempt from this PC, then map the export downloads after login (holdings plus orders `LoadDocstore.xls`). Barclays is not deployed as a download step yet.
3. **Matching:** 2 unmatched orders in production (Data → Matching). One is the HL BCHS sale, probably because the holding shows as closed. The Barclays buys matched to another account's holding also need checking.
4. **Housekeeping on the Surface:**
   - prune older DB snapshots in `/var/backups/stocks/` (keep the newest and `stocks-install.kOvgvno0.db`);
   - drop the stash "pre-deploy WIP 2026-09-23" once happy (it was verified identical to commit 57d2262);
   - remove the old release `/opt/stocks/releases/stocks-install.kOvgvno0` once the new one has proven itself.
5. **Housekeeping on this PC:** drop the stash "pre-merge local WIP" (also backed up in `~/.local/share/stocks-db-backups/local-wip-*`). The local `portfolio.db` is stale, so refresh it from the Surface master (skill `surface-stocks-db-sync`) and never push it the other way.
6. **Later:**
   - pre-existing lint (30) and mypy (23) debt;
   - `test_surface_installer` fails on an already-installed host, so skip it there;
   - Playwright uses the ubuntu24.04 fallback build on the Surface (26.04), so re-check this after Playwright upgrades;
   - optional Bedrock LLM repair (phase 4) is not started.
7. If the HL password changes, update both `.env` (PC) and `/etc/stocks/brokers.env` (Surface), then delete any `hl-login-blocked` marker.
