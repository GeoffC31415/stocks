# Passkeys and Broker Isolation Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement and independently review each workstream.

**Goal:** Enable Dashlane-compatible single-owner passkeys and revocable sessions, and separate public web and broker worker identities/state without disrupting current access.

**Architecture:** Keep https://solarpi.hopto.org:5000 (user selected no DNS change). Use a maintained Python WebAuthn verifier and browser helper, separate private SQLite auth state, one-use expiring ceremony challenges, required user verification, secure opaque sessions, and exact-origin protection. Preserve explicit Basic migration mode until real Dashlane enrollment/login verification; final passkey mode has no Basic/password fallback. Retain web identity stocks, introduce stocks-sync with private broker state and minimal shared DB/status handoff. No production portfolio tests, secrets in output, or blind activation.

**Tech Stack:** FastAPI/ASGI, py_webauthn, SQLite, React/TypeScript, @simplewebauthn/browser, systemd/Caddy, pytest/Vitest/Playwright.

## Task 1: Isolated branches and baseline

Create separate worktrees rooted at base 77160ef876db6bce8317d227e46678e7b1fe45cf. Original checkout contains unrelated local documentation; preserve it unchanged. Live /opt/stocks/current is root-owned and not edited. All tests disable dotenv before importing configuration, use in-memory/disposable DBs, and forbid broker calls/startup on real data. No live-data backup is needed for synthetic work; privileged activation requires SQLite-aware verified backups first.

## Task 2: Auth persistence and ceremony verification

Files: backend/app/passkeys.py (new service/store), backend/app/routers/auth.py, backend/app/config.py, backend/tests/test_passkeys.py; requirements.txt and requirements-production.in/lock.

Vertical TDD: first reject missing/expired/replayed challenge; implement bounded persisted challenges bound to browser preauth cookie, operation and registering identity; then verify registration and assertions using py_webauthn with exact configured origin, RP hostname without port and required user presence/verification. Use discoverable credentials, no public signup. Test bad signature/origin/RP/user verification, replay, duplicates, unknown credentials and synced-passkey zero counters with real generated cryptographic fixtures.

Auth DB separate from portfolio/broker DB. Store only public credential keys, random owner handle, hashed opaque session/ceremony cookies and metadata; never private keys or reusable passwords. Enforce strict permissions, bounded rows, expiry cleanup and atomic one-time consumption. Opaque random HttpOnly Secure SameSite=Strict __Host-stocks_session cookie (no Domain; Path=/), idle 24h and absolute 7d default. Persist revocation across restarts. No session tokens in JS storage or logs.

## Task 3: Boundary, migration, management and recovery

Files: security.py, main.py, routers/auth.py, app/auth_cli.py, web security regression tests.

Explicit auth_mode basic|passkey (basic preserves deployed migration access). In basic mode existing auth remains required for portfolio/UI; first registration is allowed only with verified existing Basic credentials and exact Origin. Registration issues passkey session for testing. In passkey mode ignore/reject Basic, permit only narrow login/status/auth/static shell paths without sessions; every sensitive API remains protected. Additional enrollment, credential revocation and logout-all require recent passkey verification (5 minutes); last credential cannot be removed from web UI. Login itself provides step-up. Logout/current/all sessions are real revocations. Generic errors and existing host/CSRF/body/security headers remain.

Local administrator CLI can revoke sessions and create a bounded one-use recovery enrollment token saved exclusively to a private local file, not printed or accepted in chat. Recovery never silently restores public password fallback. Treat recovery authorization as a separate ceremony operation, bind it to a preauth cookie, rate-limit and invalidate after use. CLI must take an explicit auth store path; no portfolio imports/migrations. Document secure local handling and second authenticator enrollment.

### Shared frontend/backend API contract

- GET /api/auth/session -> {mode: local|basic|passkey, authenticated: boolean, passkey_authenticated: boolean, can_register: boolean, expires_at: number|null}; no private info anonymously. Local mode is authenticated for normal local requests.
- POST /api/auth/login/options {} -> {ceremony_id: string, options: PublicKeyCredentialRequestOptionsJSON}.
- POST /api/auth/login/verify {ceremony_id, credential} -> same session JSON, sets cookie.
- POST /api/auth/register/options {label: string} -> {ceremony_id, options: PublicKeyCredentialCreationOptionsJSON}; registration authorization as above.
- POST /api/auth/register/verify {ceremony_id, credential} -> session JSON, creates passkey and session. Bind label in ceremony, not verification body.
- GET /api/auth/credentials -> {credentials: [{id:string,label:string,created_at:number,last_used_at:number|null}]} authenticated; never private key.
- DELETE /api/auth/credentials/{id} -> {ok:true}; recent passkey required, reject removing last.
- POST /api/auth/logout {}, POST /api/auth/logout-all {} -> {ok:true}.
- Errors {detail:string}, fixed safe messages; status 401 means auth required, 403 recent verification/Origin forbidden, 409 last-passkey/conflict.
- Recovery API/UI contract may be added but must be coordinated before implementation.

## Task 4: Frontend login and management

Files: frontend/src/auth/* (new), main.tsx, lib/api.ts, frontend tests, package.json/lock.

TDD vertical slices: auth gate prevents portfolio mount/network requests until authenticated; sign-in handles cancellation with a retry action; passkey setup button saves to Dashlane or other standards-compliant provider; security panel manages passkeys/add backup/re-auth/revoke/logout-all. Add always-accessible security and logout controls. Use @simplewebauthn/browser, no manual binary encoding/crypto. Clear QueryClient caches on logout/expired API401 so another browser session cannot see stale portfolio data. Never store session/recovery credentials in localStorage or URL query. Preserve SPA deep links and existing local/basic mode behaviour. Test accessible loading/errors and no redirect to arbitrary origins. Gaming PC is the user's first enrollment device; browser not yet specified.

## Task 5: Broker identity and data handoff

Files: deploy/stocks.service, stocks-sync.service, isolated deployment migration helper(s), sync status config/service/runner, public broker route guards, targeted tests and docs.

Retain web User=stocks; worker User=stocks-sync, separate 0700 /var/lib/stocks-sync browser/inbox. Shared portfolio database in group-restricted /var/lib/stocks-data, both identities permitted only this necessary shared write surface; auth state stays private to web under /var/lib/stocks. Worker publishes only sanitized status to dedicated /var/lib/stocks-status, web read-only and worker writable. Web must not access worker profile/inbox/credentials or inject tasks. Worker environment must not include website authentication secrets; web environment must not include broker secrets. Disable direct web broker calls in public mode; preserve narrowly authorized fixed service trigger if explicitly enabled. Separate writable lock location for trigger from worker inbox if needed.

TDD: tests prove public broker routes fail before DB/network dependencies; status path is independent of inbox; unit/config migration fixture tests verify different identities, restrictive paths, no secret output, permissions/WAL sidecar handling. Migration scripts require root, validate intended host/state, stop timer/services in safe order, create exclusive private verified snapshots, preserve originals and units/config, split env with strict key policy, migrate only expected state, install unit paths, and verify OS access controls before activation. No automatic broker login for smoke tests. Rollback must restore coherent DB/config/units, not only symlink. No sudo password in script argv/stdin/chat.

## Task 6: Integrate and independently review

Parent merges worker commits into security/passkeys-isolation-20260927. Spec review first; fix gaps. Fresh security/quality review next: challenges/session fixation/recovery/CSRF/route exemptions/storage/identity/migration rollback. Reviewers must not modify source. Parent tests exact merged candidate and records baseline failures honestly. Audit resolved dependencies. Production build output and any TLS rehearsal stay outside live dist/data.

## Task 7: Production-equivalent rehearsal and release preparation

Synthetic app with disposable portfolio and auth DB, TLS proxy matching production cookie/origin rules, Playwright virtual authenticator for enrollment/login/logout/revocation/unauthenticated requests. Exercise live crypto, not only mocked verifier. Auth state survives process restart; revoked sessions do not. Backend must reject wrong origin/Basic after final passkey mode. Validate systemd/parser scripts and candidate hash-locked install/build on production Python. Stage release only after tests/reviews pass.

## Task 8: Privileged migration and owner enrollment gates

Administrator sudo approval on Surface is required (currently not cached). Do not bypass. First deploy isolated services in Basic migration mode, verify no unintended access and original portfolio consistency using authorized metadata-only checks. User then enrolls Dashlane from gaming PC at existing HTTPS origin and tests passkey authentication; encourage second independent passkey. Only after that evidence enable passkey-only mode, verify old Basic cannot access APIs, and verify persistent session/logout. If unavailable, deliver tested implementation and exact pending activation/enrollment steps, explicitly NOT 'live/complete'. Preserve Grafana, hostname and existing external forwarding. No remote push requested.

## Completion ledger

Track task-1 through task-8 separately. 'Prepared' is not 'activated'; virtual authenticator is not Dashlane; source isolation is not verified OS isolation. User requested both plans; never call the whole task complete with either gate outstanding.
