# Barclays automation — verified progress and blockers

## Status

**Not complete; not deployed. Do not enable unattended Barclays authentication.**

The user restored access and manually authenticated in an isolated visible Chromium profile on the Surface. No automated credential submission was performed in this investigation. The user explicitly requires fully unattended login, not a login-assisted substitute.

## Evidence

- Real post-login export collector succeeded using the authenticated account Overview, Orders, then History.
- Holdings export endpoint: same account `/Portfolio/InvestmentsOverview/GetInvestmentsFile`.
- Order export endpoint: same account `/Orders/History/GetDocumentFile`.
- Browser download events returned zero-byte artifacts despite reporting no failure. Exact observed export GETs using the existing browser session returned valid XLS files; retries and redirects were disabled.
- Private exports were classified and parsed: 14 holdings/cash rows (one cash row), 392 completed orders. Every holding had a finite GBP valuation. These counts do not prove complete broker history or snapshot completeness.
- No production database import or service/configuration change was made.
- The isolated review session was logged out and its debugging listener was confirmed closed.

## Development changes

- Authentication attempt marker is created exclusively and fsynced before bank interaction. Cancellation, exceptions, ambiguous authentication and restart retain the marker. It is not cleared automatically in this incomplete implementation.
- Positive authentication check requires the investments hostname and logout control, rather than merely a non-login URL.
- `read_export` restricts requests to the exact HTTPS host, current account and observed export endpoint. It rejects redirects, non-200 status, empty/oversized bodies and wrong content types (by content classification).
- `collect_exports` returns both classified exports in memory, without publishing inbox files or database writes.
- `fetch` remains explicitly disabled when configured, and skips when unconfigured. Credentials alone cannot enable unattended authentication. The collector is deliberately not wired to the scheduled importer.

## Verification

- Final focused safety/export/scheduler tests: 38 passed, independently rerun by parent.
- Changed-file Ruff and diff whitespace checks passed.
- Final full suite: 687 passed, 9 failed. An isolated HEAD checkout reproduced the identical 9 failures (652 passed): missing local HL fixtures, FastAPI route-introspection compatibility, installer checks refusing an already-installed Surface, and absent `/usr/bin/google-chrome`. Intermittent aiosqlite teardown warnings also exist in baseline.
- First independent review found a cross-account race after the History click. A separate fixer added account pinning before all awaits, validation before requests and after body reads, public-boundary error sanitization, and regression tests. Operator messages no longer suggest deleting markers to retry.
- Fresh independent review passed the final code as disabled safety groundwork: no blocking security concerns or logic errors. This is not approval to enable unattended authentication or a claim that the integration is complete.

## Safe release preparation

The approved deployment scope is the reviewed, disabled Barclays safety/export groundwork only. It must not enable unattended authentication, import the investigation exports, or alter HL/Trading 212 credentials or schedules.

- Existing default branch was `master`; `main` is being published separately at the user's request without changing the remote default.
- `deploy/upgrade-surface.sh --prepare-only` built a private production release successfully. Frontend typecheck/build and production import smoke test passed.
- An isolated production-runtime probe supplied synthetic Barclays settings and verified that `fetch` returns `needs_attention` without invoking login.
- Frontend suite: 183 passed, 2 failed; the exact two display-format failures also reproduce on the unchanged baseline. Ruff and mypy comparisons found no new diagnostics.
- Activation still requires interactive administrator authentication. Preparation is not deployment. The activation script takes an integrity-checked SQLite backup before switching releases and checks the authenticated service/proxy boundary.

## Remaining acceptance gates

1. Establish a permitted unattended authentication mechanism, securely provision it, and verify a single controlled authentication without risking repeated attempts. The successful manual login does not establish the cause of the earlier automated lockout.
2. Map and verify the authentication-to-investments account transition; current collector requires an already authenticated account Overview.
3. Verify intended account coverage, order date/filter coverage, and fail-closed snapshot completeness—not just file classification.
4. Integrate a transactional pair import with canonical services, including rollback and idempotency tests. The existing generic inbox importer commits files separately.
5. Rehearse against a copy of the production master, perform reviewed deployment with a backup, then verify one complete scheduled run. Root access was unavailable in this session; no production credentials were read.

Private broker exports and browser profile remain outside the repository. Do not copy them into fixtures, commits, logs or review prompts.
