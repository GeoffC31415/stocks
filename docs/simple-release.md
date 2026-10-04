# Deployment and recovery

## Source and entrypoint

Master is the sole pre-deployment truth. Integrate, check and publish authorized
changes to `origin/master` before packaging. The home script fetches remote master;
it does not deploy dirty files, a detached worktree or whatever release was retained.

The **only deployment entrypoint** is `/home/geoff/deploy-stocks-master`, run as
Geoff on the Surface, not prefixed with sudo. Read its current implementation before
use. Preparation (builds, tests and writes private artifacts; not read-only):

```sh
/home/geoff/deploy-stocks-master --prepare-only
```

Attended activation, only after explicit release approval and local administrator readiness:

```sh
/home/geoff/deploy-stocks-master
```

The script fetches a private master ref, exports fresh application source, installs
frontend dependencies, runs frontend tests with two workers/typecheck/build, packages
against its pinned runtime seed, and prepares/inspects a bundle. Its receipt binds
revision, digest, bundle, expected current pointer and unique operator unit.
It does not run the full backend suite: run relevant backend checks before publication.

Preparation alone is **not deployed**. Before approving activation, verify the export
includes `backend/app/trading212_cli.py`, dedicated request/status routes, and built
frontend service requests. Review installed worker policy/runtime access separately;
a source match or synthetic preview cannot prove the protected policy permits execution.

## Safety contract

The installed controller is an internal dependency, not an alternative deployment
workflow. The script checks pinned tools/runtime, storage/schema/startup/proxy
compatibility and the shared sync-lock contract. An incompatible change needs a
separately reviewed upgrade, not a force flag or modified installed release.
Do not run one-time install/adopt/isolation/passkey-cutover helpers or legacy installers.

Activation uses a unique managed operator unit and expected-current guard, rehearses
as real service identities, and serializes against the existing stable sync lock.
A busy worker is not killed. The timer is paused/restored only under its guarded
window; no implicit missed-run catch-up, broker smoke, DB restore or unit rewrite.
Do not edit protected release/configuration/state paths to make a refusal pass.

## Verification and failure

Keep the original terminal/unit identity and exit result. On interruption, timeout
or refusal, retain receipt/journal/evidence and inspect the **original** operation;
do not rerun. Running/attention state blocks ordinary retries. Native administrator
approval belongs in the local prompt, never chat or process input.

Success requires exact pointer/source/artifact readback, stable backend **and** proxy
process identities/PIDs, and verified timer restoration. Anonymous HTTPS health 401
proves only authentication refusal, not authenticated portfolio health. Sign in,
check portfolio/classifications, passkey logout and dedicated worker request/status
behaviour as separately authorized; a real broker request is not a harmless smoke test.

For an unsuccessful transition, establish whether old web was actually restored
and whether the timer is paused. Recovery is a separately approved controller
operation bound to its exact recorded operation and freshly observed pointer;
there is no safe static rollback command to copy. Never repoint current manually,
re-adopt to bypass attention, delete markers, enable a paused Persistent timer
without catch-up approval, or use legacy data-restoring rollback for a code release.
No documentation here asserts that current master is live.
