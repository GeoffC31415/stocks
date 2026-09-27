# Passkeys and broker isolation: candidate verification

## Current completion-redesign status

The focused redesign is code-complete and independently approved within development scope. Source commits55907c1 ande8d4354 were integrated as232980c and7fc1120. The independent security review `/tmp/stocks-completion-redesign-quality.md` found no remaining concrete blockers, reran244tests and exercised four additional real-publication/interrupted-return scenarios with mocked host operations. Completion records now identify candidates, not permission to resume: both scheduling and passkey cutover require fresh matching live identity and configuration. Historical failure/commit ambiguity and external scheduling races remain explicitly documented in `docs/completion-state.md`.

Parent integrated regression run:320passed across completion, probe-schema, migration, host, deploy, broker isolation, cutover, sync-control/locks/policy and the revised synthetic root-rehearsal tests. Scoped Ruff initially found four style issues in two new test files; imports/dict-literal formatting were corrected without changing production code.

The synthetic rehearsal launcher fix6c5afde is integrated as50f25e2, independently approved for separately authorized execution, and passes40nonprivilegedtests. Actual privileged namespace/cross-UID/WAL acceptance is still NOT established: the earlier run failed before startup, and the replacement approval question timed out. No further prompt or retry was opened. No production deployment, authentication change, broker run or schedule resumption follows from these development approvals.

The chronological checks below retain superseded failures and the evidence leading to the redesign.

Candidate integration branch: security/passkeys-isolation-20260927 in /home/geoff/code/stocks-security. Source baseline 77160ef876db6bce8317d227e46678e7b1fe45cf. Original checkout and live release untouched during development. This is not a live activation record.

## Executed tests

- Runtime-equivalent Python 3.14.4 venv built from /usr/bin/python3, hash-locked production requirements installed with --require-hashes --only-binary=:all:. Test-only pytest/pytest-asyncio/openpyxl added separately.
- Integrated full backend: 933 passed, 7 failed, 3 warnings. JUnit /tmp/stocks-security-candidate-backend.xml. Compared exact failure test identities programmatically against /tmp/stocks-security-backend-baseline.xml: identical seven baseline failures. No private fixtures fabricated. Runtime warnings include existing long worksheet name and Python3.14 fork/thread warnings.
- Integrated frontend: 211 passed, 2 failed, matching baseline AllocationDonut/formatters compact-currency assertions. JSON /tmp/stocks-security-candidate-frontend.json. Typecheck and production build passed; existing large-bundle warning remains.
- Targeted security/auth/rehearsal safety: 186 passed on the production-equivalent interpreter.
- Standalone root-rehearsal guard tests: 15 passed. This alone does NOT prove privileged namespace/DAC/WAL behaviour.
- Auth development environment pip-audit: no known vulnerabilities among the 49 distributions then present; frontend production npm audit: zero advisories. Test environment later added openpyxl separately. Exact staged-runtime audit remains a release gate.

## Real browser and HTTPS rehearsal

Harness scripts/verify_passkeys.py runs Caddy internal TLS on loopback-only high ports, no public ACME or trust-store installation, exclusively created scratch state and a guarded backend refusing SQLite paths outside that scratch directory and outgoing Internet sockets. Browser traffic restricted to the rehearsal origin. Credentials/authenticator/data are synthetic only.

The first baseline run failed because the old application had no auth session endpoint (expected RED). Initial API-first enrollment rehearsal passed but missed a UI integration bug: Security queried the passkey-only credentials endpoint before first enrollment, receiving401 and locking the UI. Independent SPEC review found this; the harness was upgraded to click the real Security button, fill Passkey name and click Add passkey. It reproduced the failure against the original candidate and passed after scoped fix524b661 (integrated0ad1c39).

An early login readiness probe also ran ahead of the actual verification response. The final harness waits for the completed login/verify response plus the authenticated Log out control and then verifies a protected API; it does not rely on an asynchronous polling predicate.

Final pre-review evidence: /tmp/stocks-passkey-bootstrap-green/report.json, result passed, children_stopped true. All eight grouped checks:

1. TLS validates against the private test CA; anonymous API denied; Basic migration explicit.
2. Built frontend first enrollment works under Basic, using a real resident CDP authenticator with required UV; ceremony replay denied.
3. Browser issues Secure/HttpOnly/SameSite=Strict __Host session cookie.
4. Session survives backend restart; explicit passkey-only mode rejects the old valid Basic credentials; anonymous login shell is available.
5. Wrong/missing Origin rejected, and same-origin authenticated synthetic create/read/delete is persisted and read back.
6. Logout revokes replayed old cookie; built frontend completes a fresh real WebAuthn login.
7. Independent virtual backup device enrollment succeeds; old credential revocation succeeds; last-key deletion is refused; logout-all revokes saved token.
8. Local recovery CLI writes private0600 token file without token output; browser recovery grant is one-use; successful recovery replaces old credentials and restores access.

Screenshots in that directory are synthetic. Earlier sign-in/mobile captures were visually inspected: new auth controls are legible and not clipped; existing mobile portfolio fixed-navigation overlap remains outside this auth change. Dashlane itself has NOT yet been enrolled or tested.

## Review gates

- Broker SPEC d64f19c initially failed timer-resume partial rollback/reconciliation. Fix58a4523 received independent SPEC PASS; 102 targeted tests independently passed. Security review found missing fail-closed cleanup after rollback restart. Fix8fed2ab (integrated a692e0c) adds health/marker/interruption/cleanup-failure regressions; 106 targeted tests passed in the implementation worktree. Parent independently ran migration, cutover and synthetic-rehearsal suites together: 91 passed. Focused independent rollback re-review withheld approval: a completion-marker fsync failure after creation leaves rollback-complete present, allowing a later explicitly authorized timer resume to accept the failed transition. Health-failure cleanup was confirmed fixed. The second focused correction5ce8d29 (integrated6b8a470) adds guarded activation/rollback completion publication and a pending veto if invalidation fails. Parent ran all migration/host/deploy/broker/cutover tests, including the unprivileged CLI guard:136passed, no deselection. Final independent completion-marker review withheld approval: interruption after successful pending-marker removal, combined with failed completion invalidation, leaves an accepted completion despite reported transition failure. Both activation and rollback were independently reproduced with mocked host commands; later explicit resume requested timer enable/start. No automatic resume or remote exploit is claimed. Report: /tmp/stocks-isolation-completion-final-review.md. The two focused fix cycles are exhausted; further edits and deployment are paused for escalation and an agreed redesign/review scope. No deployment approval follows from the passing test counts.
- Passkey SPEC initial bootstrap UI mismatch corrected as above. Independent security review approved the backend/frontend; 183 backend and22frontend auth tests independently passed. Minor recovery-label limit corrected from100to80 with observed red-to-green; parent frontend focused suite23passed and typecheck passed.
- Privileged synthetic rehearsal was independently approved for execution safety. Its SQLite creation-mode defect was corrected in01dc1f9: exclusive0660 precreation and mode=rw; 19guard/real unprivileged SQLite tests passed. This supersedes the earlier15-test result, but does not establish cross-UID/namespace acceptance. The Surface terminal attempt ended with sudo timeout (wrapper exit1); the privileged script did not run. No automatic retry is authorized by that timeout.
- Passkey cutover helper passed independent focused re-review: timer restoration must precede authentication-mode cutover after separate catch-up approval, or remain deliberately deferred for a separately reviewed resumption procedure. Release-ancestor ownership is checked before and after replacement. Independent11tests and four ancestor-ownership rejection probes passed. Real owner authentication and production verification remain separate gates.

## Subsequent approved privileged synthetic attempt

The owner approved a fresh Surface terminal attempt. Wrapper evidence `/home/geoff/.cache/stocks-isolation-rehearsal-retry2.json` records exit1, not the terminal launcher's exit0. Synthetic report: `/var/tmp/stocks-isolation-rehearsal-nrkv765h`, passed=false, checks=[], cleanup=true. The journal for `stocks-rehearsal-9e96e60acc2844de82e08af99c87f622-0-0.service` shows systemd rejected absent-NSS numeric user60000 at step USER (217), before the Python probe ran. Parent readback confirmed LoadState=not-found, ActiveState=inactive, SubState=dead, MainPID=0. This establishes a rehearsal setup failure, not DAC/namespace/WAL acceptance. No production operations occurred. A nonprivileged, test-first fixture correction and independent safety review are required before another separately approved root run.

## Live gates still outstanding

Privileged synthetic identity/namespace/WAL execution, immutable release staging and audit, root migration preflight and verified backups, actual live unit/private-state access checks, authenticated production read, owner Dashlane gaming-PC enrollment+fresh verification, passkey-only cutover and readback, and deliberate timer resumption. User confirmed availability to approve a terminal prompt on the Surface. No production migration, authentication change, secret rotation or broker login has occurred during the recorded development checks.
