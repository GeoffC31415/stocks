# Isolation completion: candidate evidence, not authorization

This describes a development candidate, not a deployed or production-verified
system. Independent specification/security review and operator approval remain
required. Tests use synthetic state and mocked host/network adapters.

## Version 2 evidence

The private immutable `manifest.json` saves the transition ID, bundle, old/new
release, original service state and configuration hashes. The installed
`/etc/stocks/isolation.json` binds that bundle and ID. The strict mutable
`transition.json` binds the manifest digest and records activation or rollback,
`preparing` or `verified_candidate`, and the observed boot ID, web InvocationID
and effective web-unit fingerprint. A rollback restoring an originally inactive
web has no live identity and is not resume-ready.

Preparing is published before transition mutation. Rollback preparation supersedes
activation eligibility; successful verified rollback may permit a separately
approved resume, never passkey cutover. Original state/configuration and later
recovery evidence remain private. Old state-progress markers are layout evidence,
not authorization. Legacy completion/pending files, missing records, duplicate JSON
keys, malformed or unknown schemas cannot authorize a v2 operation. There is no
automatic evidence upgrade: preserve originals and arrange reviewed manual
recovery. Do not manufacture a candidate or remove markers to bypass refusal.

## Independent decision at each consumer

Activation, rollback, resume and cutover serialize through the root-controlled
`/etc/stocks/.completion.lock`; unsafe metadata and contention refuse. This is
advisory locking among cooperating commands, not exclusion of an unrelated root
administrator. Operationally exclude all other configuration/release writers.

Resume and cutover validate the candidate against saved original hashes,
installed release/configuration, and fresh bounded read-only service probes.
They require an active, stable web with the same boot, InvocationID and effective
configuration, an inactive worker and a valid timer state. They repeat checks
before mutation and never start/reload/repair web merely to pass readiness.
A restart, reboot, drift, unavailable probe, or stopped web refuses old eligibility.

Activation, active-web rollback and resume require timer disabled/inactive.
Cutover instead requires exactly the manifest's saved enabled/active timer state,
allowing the documented **resume before cutover** order. Approve Persistent timer
catch-up separately; wait for any worker run to finish before attempting cutover.
Deferring restoration when the saved timer was active is not supported by this
cutover path. Resume verifies timer readback; failures attempt disable/stop and
report unconfirmed cleanup explicitly. Stopping the timer cannot undo a job it
already triggered. Post-cutover configuration intentionally fails the one-off
isolation resume helper's Basic-mode coherence check.

## Publication and failure limits

Record publication uses an exclusive same-directory temporary file, flush and
file fsync, close, atomic replace, directory fsync and metadata/content readback.
Atomic visibility is not durable success: a record can be visible after replace
although directory fsync, close, readback, or the caller subsequently fails.
Partial temporary evidence may remain. No deletion of the candidate or pending
marker is needed to invalidate authorization.

Caught activation/rollback failures attempt to stop services; failed cleanup is
reported as unconfirmed, not as a successful stop. If web stops, fresh consumers
refuse. If stopping itself fails and independently observed state still satisfies
all safety checks, a later explicitly approved operation is a **new readiness
decision**, not proof the failed process completed successfully.

SIGKILL, power loss and storage failure cannot guarantee cleanup or establish
historical process success. Persisted evidence alone never establishes current
readiness. Preserve evidence and inspect current state privately; do not infer
success from a visible record or promise rollback of already-triggered work.

## Gates outside these helpers

Stage a complete immutable root-controlled release and inspect effective units
and overrides. Rehearse real service identity/DAC and mount-namespace isolation
on a disposable host. Independently verify authenticated owner application health
and recovery. Anonymous HTTP/HTTPS 401 checks establish only that boundary;
they do not prove authenticated health, correct portfolio rendering or isolation.
Passkey cutover retains recent real authentication, owner and private-backup
checks, second preflight, and no automatic Basic restoration. See the
[isolation runbook](broker-isolation.md) and [cutover runbook](passkey-cutover.md).

## Development verification

The six required completion/migration/host/deploy/broker/cutover suites passed
171 tests on resumption. Expanded verification including sync-control, sync-lock,
sync-policy and UI-rehearsal tests produced **214 passed, 1 failed**. The UI
rehearsal failure is `test_rehearsal_uses_its_own_read_only_database_and_blocks_writes`:
FastAPI's `_IncludedRouter` has no `.path`. An isolated archive of baseline
`84cb56d` reproduces the same failure (**7 passed, 1 failed** for that suite).
It is not changed or bypassed by this redesign. Scoped Ruff and `git diff --check`
pass. No privileged rehearsal, deployment, live service, broker or private database
access was performed. Independent parent SPEC/security review is still required.
