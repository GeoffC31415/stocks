# Passkey frontend

The real entrypoint mounts AuthProvider and AuthGate before App. Session checking is fail-closed; portfolio queries do not mount until authenticated. Local mode retains the application without auth chrome. Basic migration mode exposes Security / passkeys and explicitly says the old browser password remains required until operator cutover. Passkey-only mode offers no Basic fallback.

## Owner enrollment (not performed by this change)

Use the gaming PC's normal browser at **https://solarpi.hopto.org:5000**. Keep the existing Basic access method during migration. Open Security / passkeys, name the first key (for example Gaming PC), choose Dashlane in the browser's passkey chooser, and complete user verification. Use Verify passkey again to test it. Add an independent backup credential and test that too. Only an administrator should then switch the backend to passkey-only mode. This frontend does not change deployment configuration, databases, service users, or worker isolation.

## Session and recovery behavior

All API transports use same-origin cookies and notify the gate on 401. Lock/logout clears query and mutation caches, aborts outstanding fetches and browser ceremonies, and rejects late session/data completions. Local logout immediately hides data; if server logout fails, a retry warning remains rather than claiming success. Logout-all requires explicit confirmation and retains the session with an error on failure. Additional enrollment/removal/logout-all can require recent verification: on 403, verify explicitly and retry the intended action. The final credential cannot be removed in the UI; the backend must independently enforce this.

Recovery is an explicit sign-in form using a locally provisioned one-time token. It is never placed in URLs, storage, query keys, or logs; the field clears immediately on submission and on unmount. Failed recovery asks for an administrator-issued token, not an email reset or password fallback.

The API contract uses `/api/auth/session`, `/login/options`, `/login/verify`, `/register/options`, `/register/verify`, `/recovery/options`, `/credentials`, `/credentials/{id}`, `/logout`, and `/logout-all` under `/api/auth`. Options return `{ceremony_id, options}`; verification sends `{ceremony_id, credential}` and receives session JSON plus an HttpOnly server cookie. The server remains the authority for authorization, origin checks, challenge validation, revocation and cookie settings.

## Verification

Run from frontend: `npm test -- --run src/auth src/main.test.tsx`, `npm run typecheck`, `npm run build`, and `npm test -- --run`.

Tests exercise mocked browser-helper ceremonies and synthetic transport responses, including late enrollment after logout, 401 cache clearing, first/backup enrollment, explicit recent verification, recovery and deep links. They do **not** prove real Dashlane enrollment or server cryptography. Real TLS/browser virtual-authenticator integration, independent security review, gaming-PC enrollment, backup testing and operator cutover remain separate acceptance gates.

Known pre-existing full-suite failures at handoff: AllocationDonut compact £10k formatting and the formatter's £250k expectation versus decimal output. Do not treat those as passkey regressions or claim a green full suite.
