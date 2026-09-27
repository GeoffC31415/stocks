# Passkey rollout decisions and activation gates

- Owner explicitly selected keeping `https://solarpi.hopto.org:5000`; do not change DNS/router/Grafana.
- First real Dashlane enrollment will be from the owner's gaming PC. Browser is not yet specified; use a supported browser with current Dashlane extension, signed into the intended vault. Never request its master password or passkey material in chat.
- WebAuthn RP ID is the exact hostname `solarpi.hopto.org`; expected origin includes `https://` and port `:5000`. Enforce required user verification. The server stores credential public keys, not the private passkey.
- Shared-host residual: passkeys and cookies are not port-isolated in the same way as Web origins. Exact-origin verification and CSRF protection must include the port. Secure cookies are not sent to HTTP Grafana, but another HTTPS service on the same hostname can receive host cookies. Do not claim the `__Host-` prefix isolates services by port. Moving to a dedicated hostname remains a future improvement and can require passkey re-enrollment.
- Preserve explicit Basic migration access while the first passkey is enrolled and tested; it is temporary and NOT the final passwordless security state. Final `passkey` mode must ignore Basic credentials, including browser-cached ones. Empty/missing auth storage must not downgrade to Basic or open registration.
- The backend/enrollment route must prevent an existing Basic credential from adding keys after the first registration without recent passkey verification. Browser sessions must be independently revocable and cleared in the UI on expiry/logout.
- Backup authenticator: recommend a second independent authenticator such as a hardware key. A synced copy of the same Dashlane passkey is convenient but not independent recovery if access to the Dashlane account is lost.
- Local recovery is an administrator-controlled one-use expiring enrollment grant, never an internet-accessible password reset or permanent bypass. Keep its file private; no token in chat, URLs, logs or JavaScript persistent storage.
- Service isolation needs a real OS permission check after privileged migration. Merely setting different environment files while sharing UID/state does not meet the gate. The web worker must not retain readable old browser/inbox/credential backups after migration.
- Shared portfolio DB write access is deliberate. It means either service can modify portfolio data; it does not grant access to the other's authentication/browser secrets. Explicit group and SQLite sidecar permissions must make this stable across service restarts.
- Root-only environment parsing must fail closed on unknown syntax or broker-key conflicts, preserve source values without printing them, and generate separate web/worker configs. Database backup and rollback must be SQLite-aware and coherent with unit/config changes.
- Do not automatically trigger real bank logins in deployment verification. Verify scheduling/configuration and permissions without contacting brokers; preserve the prior timer enabled/active state.

## Required live completion evidence

1. Privileged migration succeeded, saved coherent private rollback artifacts, installed release pointer matches reviewed commit, unit identities and paths read back correctly.
2. Web service cannot read worker private profile/inbox/env backups, worker cannot read web auth DB, shared DB/status permissions function as intended.
3. Existing portfolio remains available through current authorized access and protected from anonymous API requests; no unexpected migrations/provider activity.
4. Owner enrolls Dashlane on gaming PC, then performs a fresh passkey login. A virtual authenticator rehearsal is not evidence of Dashlane enrollment.
5. Operator switches explicitly to passkey-only mode only after preceding evidence. Basic authentication fails thereafter; session logout/revocation and new login work.
6. A second recovery method is enrolled or local recovery procedure is demonstrated with the owner's explicit acceptance of the remaining single-authenticator risk.

No production activation or completion claim until the applicable gates are evidenced. Staged implementation, virtual browser verification and live owner enrollment must be reported separately.
