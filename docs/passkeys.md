# Single-owner passkey backend

This is a staged migration, not a deployment instruction to run unattended.
No live service, private portfolio database, broker credentials or provider calls
were used to implement this backend. Frontend integration, independent review,
a real TLS browser exercise and the owner's Dashlane gaming-PC test are separate
release gates. Do not switch the live service before those gates pass.

## Configuration and migration

Keep the public origin exactly `https://solarpi.hopto.org:5000`. The WebAuthn RP ID
is its hostname, `solarpi.hopto.org`; the port remains part of the verified origin.

1. Prepare a release with the hash-locked runtime requirements and auth frontend.
   Keep `PORTFOLIO_DEPLOYMENT_MODE=public` and `PORTFOLIO_AUTH_MODE=basic` (the
   explicit migration mode; also the default). Existing Basic credentials remain
   required for normal APIs, pages and assets, even after passkey enrollment.
2. Set `PORTFOLIO_AUTH_DATABASE_PATH=/var/lib/stocks/auth.sqlite3` in the web
   service's private configuration. This is **not** the portfolio database and
   must not be copied into a broker worker's configuration. Provision its parent
   as owned by the actual web-service identity, preferably mode 0700, not writable
   by any other identity. The store creates the database mode 0600, rejects
   symlinks/hardlinks/permissive files, and rejects non-auth SQLite databases.
   For the broker-isolated deployment, use the private web identity, not a shared
   broker identity. Existing legacy units may still name `stocks`; change identity
   only as part of the separately reviewed isolation deployment.
3. On the exact HTTPS origin, use valid Basic authentication to obtain the first
   registration options. Only an empty auth store permits this bootstrap. Options
   are browser-bound and expire after five minutes. The verify request consumes
   that proof and requires a real user-verified passkey response. Complete the
   browser ceremony and verify a separate passkey login before cutover. Enroll a
   second recovery-capable device if desired using a recent passkey session.
4. After release gates pass, explicitly set `PORTFOLIO_AUTH_MODE=passkey` and
   restart the web service using the same auth database. Remove the obsolete Basic
   username/hash from its configuration. Passkey mode never accepts Basic, even
   if the auth store is empty: there is no automatic password fallback.
5. Verify an unauthenticated private API gets 401, the login shell loads, a real
   passkey login succeeds, logout revokes access, and revocation survives restart.
   Do not delete/reset the auth store to recover access.

Public passkey mode permits only known HTML shell routes, existing built assets,
and the explicit auth ceremonies anonymously. Financial APIs remain protected.
All unsafe public requests, including anonymous login/recovery, require the exact
Origin. Sessions use `__Host-stocks_session` (Secure, HttpOnly, SameSite=Strict,
Path=/, no Domain); only its hash is stored. Default idle expiry is 24 hours and
absolute expiry seven days. `PORTFOLIO_AUTH_SESSION_IDLE_SECONDS` and
`PORTFOLIO_AUTH_SESSION_ABSOLUTE_SECONDS` may shorten, not extend, those limits.

Adding/deleting passkeys and logout-all require passkey verification in the last
five minutes. Deleting a credential revokes its sessions; the last credential
cannot be deleted. Login rotates the current session. Challenges are atomic,
one-use, browser/purpose-bound, persisted and consumed even on failed verification.
User presence and verification are mandatory; registration requests discoverable
credentials. Real verification uses `webauthn==2.8.0`, not a signature stub.

Limits: 16 credentials, 32 sessions, 128 outstanding ceremonies (five per browser),
16 KiB auth request bodies, and a persisted 60-second attempt budget (100 globally,
20 per peer/browser). Retain reverse-proxy and Uvicorn concurrency limits. Rate
limits can temporarily deny legitimate login during abuse; they are not an edge
DDoS service. Auth state should be backed up privately; restoring an older snapshot
can resurrect old sessions/keys, so revoke sessions after a deliberate restore.

## Browser API contract

All routes are under `/api/auth`; JSON requests, same-origin cookies. POSTs with
no parameters still send `{}`. Never log recovery tokens or credential payloads.

- `GET /session`: `{mode, authenticated, passkey_authenticated, can_register,
  expires_at}`. Mode is `local`, `basic` or `passkey`; expiry is Unix seconds or null.
- `POST /register/options` with `{label}`; `POST /login/options` with `{}`.
  Both return `{ceremony_id, options}` with native WebAuthn JSON options.
- `POST /register/verify` or `/login/verify` with `{ceremony_id, credential}`.
  `credential` is the browser credential serialized with base64url binary fields.
  Returns session JSON and sets the session cookie; never returns a bearer token.
- `GET /credentials`: `{credentials: [{id,label,created_at,last_used_at}]}`.
- `DELETE /credentials/{id}`, `POST /logout`, `POST /logout-all`: `{ok: true}`.
- `POST /recovery/options` with `{token,label}` returns the same options envelope;
  finish through `/register/verify`, not a separate recovery-verify endpoint.

The preauth cookie is `__Host-stocks_preauth`, also Secure/HttpOnly/Strict. Preserve
it between options and verify. Clear private UI caches/state on logout or 401.

## Local operator recovery (no password fallback)

The CLI imports neither application settings/dotenv nor the portfolio database.
It requires an explicit **existing absolute auth database path** and must run as
its owning web-service identity. From the installed release, substitute that
identity and the actual release paths; do not run against a development copy by
accident. These are operator examples, not commands executed during verification:

```sh
cd /opt/stocks/current
sudo -u WEB_SERVICE_IDENTITY env PYTHONPATH=/opt/stocks/current/backend \
  /opt/stocks/current/.venv/bin/python -m app.auth_cli \
  --database /var/lib/stocks/auth.sqlite3 revoke-all

sudo -u WEB_SERVICE_IDENTITY env PYTHONPATH=/opt/stocks/current/backend \
  /opt/stocks/current/.venv/bin/python -m app.auth_cli \
  --database /var/lib/stocks/auth.sqlite3 recover \
  --output /var/lib/stocks/recovery-token --ttl 600
```

Use a new output filename in a private directory each time. The CLI creates it
exclusively mode 0600; it does not print the token or accept it as an argument.
Securely transfer the token into the trusted same-origin recovery UI, never into
chat, logs or shell history, and remove the token file after use. Recovery issuance
immediately revokes sessions and pending ceremonies and disables existing keys.
Old key records are retained until successful replacement registration; that
transaction removes them and creates the replacement session. The token is one-use
at options issuance (default ten-minute lifetime; allowed 60–900 seconds).
If token expiry, lost preauth cookie or failed verification interrupts recovery,
issue a fresh token locally: old keys stay disabled, with no timed fallback.
`revoke-all` revokes sessions/ceremonies but does not cancel recovery mode.

## Synthetic verification

The store tests generate actual P-256 keys, COSE public keys, attestation objects
and ECDSA assertions and pass them through the WebAuthn library. They exercise
origin/RP/UP/UV/signature/owner failures, replay, counters, expiration, restart,
recovery, file protections, bounds and CLI non-disclosure. HTTP tests forbid
portfolio connection/startup and exercise Basic-to-passkey cutover and API gates.

Run with dotenv disabled **before importing app configuration**, and a memory
portfolio URL (the disposable auth stores are pytest temporary files):

```sh
PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: PYTHONPATH=backend \
  .venv-auth/bin/python -c 'from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource; DotEnvSettingsSource._read_env_files=lambda self:{}; import pytest; raise SystemExit(pytest.main(["backend/tests/test_passkeys.py", "backend/tests/test_auth_routes.py", "backend/tests/test_web_security.py", "-q"]))'
```

Verification in this worktree: targeted passkey/HTTP/security tests **183 passed**;
full backend suite **859 passed, 7 failed, 1 warning**. The seven failures match the
reported pre-change baseline: two missing private HL CSV fixtures, three FastAPI
lazy-route-enumeration assumptions, and two installer preflights refusing an
existing systemd unit. No unrelated baseline fixes were made. Scoped Ruff and
`git diff --check` passed. `openpyxl` was installed only in the disposable test venv
to resolve collection; it was not added to production requirements. Existing
production lock versions were unchanged; WebAuthn and its dependencies were added.

These synthetic tests do not prove Dashlane compatibility, real TLS/browser
behavior, live broker isolation, or production deployment. Independent security
review and browser testing remain separate gates; this is not a full-suite pass.
