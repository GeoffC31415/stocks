# Single-owner passkeys

## Owner use and session behaviour

Use the exact HTTPS origin `https://solarpi.hopto.org:5000`; WebAuthn RP ID is
`solarpi.hopto.org` (the port remains part of the verified origin). In passkey mode,
sign in through the browser's passkey chooser and complete user verification.
Security / passkeys supports named additional credentials and explicit verification.
Keep an independently tested backup credential. Selecting Dashlane is an owner/browser
choice; server ceremony evidence cannot prove the password-manager vendor or device.

The frontend gates portfolio queries until session checking succeeds. Local mode has
no auth chrome. Basic compatibility mode still requires the browser password even
after a passkey ceremony; it must not be mistaken for completed passkey-only activation.
Do not rerun historical bootstrap/cutover instructions or edit auth configuration ad hoc.
Passkey mode never falls back to Basic, even with an empty store.

Logout hides local data immediately, clears caches and aborts requests/ceremonies.
A failed server logout retains a retry warning, not a false revocation claim. API 401
locks the gate; late data/session completions are rejected. Additional enrollment,
credential deletion and logout-all require verification within five minutes; verify
and retry explicitly when refused. The backend refuses deletion of the last credential.

Sessions use a Secure/HttpOnly/SameSite=Strict `__Host-stocks_session` cookie with
Path=/ and no Domain; only its hash is stored. Default idle expiry is 24 hours,
absolute expiry seven days; configured overrides may shorten, not extend them.
Deleting a credential revokes its sessions; logout-all revokes all sessions.
Challenges are persisted, atomic, one-use and browser/purpose-bound with required
user presence/verification. Do not log recovery tokens or credential payloads.

## API and storage

[Auth router](../backend/app/routers/auth.py),
[store](../backend/app/passkeys.py) and
[frontend auth](../frontend/src/auth/) are the contract.
Routes under `/api/auth`, with same-origin cookies:

- `GET /session`: mode, authenticated/passkey-authenticated state, registration permission and expiry.
- `POST /register/options` with `{label}`; `POST /login/options` with `{}`.
- `POST /register/verify` or `/login/verify` with `{ceremony_id, credential}`.
- `GET /credentials`; `DELETE /credentials/{id}`; `POST /logout` and `/logout-all`.
- `POST /recovery/options` with `{token,label}`, completed through `/register/verify`.

Options return `{ceremony_id, options}`; verification returns session JSON and sets
an HttpOnly cookie, not a bearer token. Preserve the secure preauth cookie between
options and verify. Unsafe public requests require exact Origin, including anonymous
auth ceremonies. Financial APIs remain protected.

The auth SQLite store is **separate from the portfolio DB**, owned by the web identity
under its private directory. The store rejects unsafe file permissions/links and
non-auth databases. Keep backups private: restoring old auth state can resurrect old
sessions/keys; deliberately revoke sessions after a reviewed restore.

## Local recovery

Recovery is an explicit administrator action, not an email reset or password fallback.
[app.auth_cli](../backend/app/auth_cli.py) imports neither dotenv/settings nor portfolio
DB. It needs an existing absolute auth DB path and runs as the owning web identity.
After verifying the actual installed identity/release, an authorized local operator
can use these templates (not deployment commands):

```sh
sudo -u stocks env PYTHONPATH=/opt/stocks/current/backend \
  /opt/stocks/current/.venv/bin/python -m app.auth_cli \
  --database /var/lib/stocks/auth.sqlite3 revoke-all

sudo -u stocks env PYTHONPATH=/opt/stocks/current/backend \
  /opt/stocks/current/.venv/bin/python -m app.auth_cli \
  --database /var/lib/stocks/auth.sqlite3 recover \
  --output "${PRIVATE_NEW_TOKEN_FILE:?Set a new absolute web-private path}" --ttl 600
```

Recovery issuance immediately revokes sessions/ceremonies and disables existing keys.
The token is written exclusively mode 0600, never printed or passed in argv. Transfer
it only into the trusted same-origin recovery form, never URLs/chat/logs/history;
remove the private token file after use. It is one-use at options issuance with a
60–900 second lifetime. Successful replacement registration removes old key records.
Interrupted/expired recovery requires a fresh local token; old keys remain disabled,
with no timed fallback. `revoke-all` does not cancel recovery mode. Never delete/reset
the auth store to recover access. Real TLS/browser/passkey/logout testing remains
separate from mocked frontend or synthetic cryptography tests.
