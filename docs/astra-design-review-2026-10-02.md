# Stocks deployment review
## Why this became difficult, and a simpler way forward

**Independent architectural review by Astra — 2 October 2026**

**Recommendation:** keep the restored production site unchanged. Do not resume the interrupted deployment work automatically. Agree a much smaller deployment design, then prove it against real service identities and a real failed start before the next production attempt.

This is a review and recommendation, not approval to deploy or a complete security audit. I inspected the session record, incident reports, measured session statistics, relevant application/service code, the exact host-v3 deployment implementation, the sealed artifact manifest, and the interrupted r2 changes. I did not run deployment code, change services, read protected credentials/databases, modify application or deployment source, or restart agents. The latest live recovery is reported from the earlier verified checkpoint, not independently re-certified here.

---

## 1. Executive assessment

The central failure was **building an increasingly elaborate proof that a deployment was authorised and internally consistent, without first proving that the packaged application could run and recover under its actual operating conditions.**

This was not simply bad luck with Python permissions. The design encouraged the wrong ordering of work:

1. Detailed historical evidence, identity fingerprints and completion records became prerequisites for an ordinary upgrade.
2. Each real-world mismatch produced another specialised guard, exception, helper or manifest.
3. Reviews tested those mechanisms rigorously, but often against fixtures sharing the implementer's assumptions.
4. Basic operating contracts—service-account access, real startup, failed-unit behaviour—were tested too late.
5. Recovery depended on much of the same machinery that had just failed.

The previous model did substantial useful work: it found genuine rollback defects, respected credential boundaries, preserved the approved UI, built failure tests, and ultimately restored the old site. Nevertheless, its overall engineering judgement was poor. It repeatedly treated local correctness improvements as progress towards release readiness without reassessing whether the whole mechanism was appropriate.

**My verdict: the security goals were sensible; the deployment architecture and execution process were disproportionate and brittle.** A personal site still needs strong data protection. It does not need a new, release-specific deployment framework for each upgrade.

### What matters most

| Finding | Consequence | Preferred direction |
|---|---|---|
| Artifact integrity was confused with runtime usability | A faithfully verified package could not start | Test the exact root-staged package as its actual service identities |
| Historical migration state became ongoing deployment authority | Normal restarts and new releases required special adoption logic | Separate audit history from present-tense operational checks |
| Recovery shared candidate-validation dependencies | A failed candidate could obstruct restoration of the known-good release | A small, separately tested recovery path |
| Deployment logic hard-coded this particular release | Every correction changed executable code, hashes and approval material | Stable operator tooling; versioned release data |
| Reviews shared the same missing environmental assumptions | Thousands of tests missed basic permissions and lifecycle behaviour | Independent real-environment acceptance, not just more fixture tests |
| Diagnostics were discarded to avoid leaking secrets | Each failure required new privileged investigation | Structured nonsecret errors plus protected diagnostic logs |

---

## 2. The morning outage was a packaging failure—not an application mystery

The new backend failed while importing `watchfiles`, before it could serve requests. The observed file was root-owned with mode `0600`: readable by root, not by the `stocks` service account.

I independently counted the modes in the sealed manifest:

| Regular-file mode | Files |
|---|---:|
| `0644` | 1,702 |
| `0755` | 23 |
| `0600` | 1,990 |
| `0711` | 53 |

**2,043 regular files lacked group/other read permission.** Not every such file is necessarily used by the application, but this was a systematic packaging-policy omission, not an isolated damaged file. The interrupted r2 reconciliation reports changing precisely those 2,043 modes while preserving file contents; that is partial work, not a tested release.

The preparation script copied the runtime and removed group/other write bits. It did not establish the positive requirement that the service must be able to read its code and dependencies. The inventory then sealed those unsuitable modes. Root validation and imports as the staging owner naturally passed.

This illustrates a crucial distinction:

> A checksum proves that these are the expected bytes. It does not prove that they are useful, executable by the intended account, compatible with the host, or safe to activate.

The missing acceptance test was straightforward: **start the final packaged application under the service's identity and relevant sandbox restrictions, using disposable data and no broker credentials.** An import-only check would have caught this particular permission error, but a full isolated startup/readiness test is the stronger contract.

Do not respond by making every file on the machine readable. Runtime code, secrets, database state, private logs and backups need different permission policies.

**Evidence:** `prepare_b6_release.py:27–34`; `upgrade_isolated.py:57–120`; sealed manifest; morning incident report.[1–3]

---

## 3. The deepest architectural problems

### A. Three different jobs were mixed together

The code blended:

- **Machine provisioning/migration:** users, groups, isolation layout, authentication configuration and service definitions.
- **Ordinary application deployment:** install one immutable release and activate it.
- **Audit and incident history:** what happened previously, under which identity, and whether a process completed.

An ordinary deployment should verify that the required machine configuration exists. It should not need to re-prove the historical circumstances in which that configuration was installed.

The code instead compared the present service with a recorded boot/invocation identity from an earlier transition. Such identities are useful for detecting a race **during one operation**. They are poor permanent prerequisites for the next operation: a normal restart changes them. This is particularly inconvenient on a Surface that can reboot or undergo normal operating-system maintenance.

The later fresh-baseline mechanism was carefully restricted and reviewed, but it was a repair to this coupling. It pinned another exact historical/current combination rather than making routine deployment naturally tolerate legitimate lifecycle changes.

**Recommendation:** retain old migration records as immutable history. For a new deployment, authorise the approved artifact and expected current release, then freshly check stable configuration, database compatibility and active work. Bind transient identities only for the duration of that operation.

This is a replacement design to review—not permission to bypass the existing guards or edit their records in place.[4]

### B. This was becoming a single-use program generator

The implementation hard-codes the application commit, old/new release paths, backend file dictionaries, Python and packaging-tool versions, artifact digests, host identity and named approval tokens. Other wrappers duplicate some of those values.

Some exact pins are appropriate **in a release manifest**. Embedding them throughout executable logic means the next release needs code changes, a new review, new code hashes and another command refreeze. The repair work had already reached multiple tool namespaces and special historical-artifact handling.

I counted **2,817 lines across the host-v3 helper, supervisor, compatibility module and outer installer**, excluding the inherited isolation module, shell batch, tests and documentation. The original helper was 147 lines. The comparison does not prove that the original was adequate—it was not—but it makes the scale change undeniable.

**Recommendation:** a stable, administrator-installed deployment tool with a small documented interface. Release-specific information belongs in one bounded, versioned manifest. The tool should validate security-relevant semantics and approved digests, not require its own source to change for every release.

A field such as an exact packaging-tool version can be recorded for provenance without automatically becoming a permanent eligibility rule. Conversely, interpreter compatibility, isolation settings and unsupported dangerous options genuinely matter. Those categories need deliberate separation.[5]

### C. “Fail closed” was not sufficiently separated from “recover safely”

Rejecting an untrusted candidate before cutover is correct. Refusing to restore a known-good service for reasons unrelated to safe restoration is an availability defect.

`restore_upgrade()` begins by validating the candidate release and configuration before restoring the previous pointer. Its recovery also uses the same stop/readiness machinery as activation. In the actual incident, systemd's `failed` state survived after the process had stopped; the code required exactly `inactive`. That blocked both automatic compensation and the first explicit recovery.

There is also a broader dependency risk: if the failed candidate becomes unreadable or its validation fails, requiring that candidate to validate before restoring the old release can make recovery unavailable precisely when needed.

This does **not** mean “always repoint the symlink.” Recovery still needs trusted previous-release identity, schema compatibility and proof that conflicting writers are stopped. The issue is identifying the **minimum sufficient recovery conditions**, rather than demanding the whole candidate's success conditions again.

**Recommendation:** establish and rehearse the recovery path before activation. It should use a trusted previous release and incident snapshot, understand stopped-but-failed units, and restore web availability independently of whether a broker schedule can safely resume. Unknown data compatibility remains a hard stop; a failed candidate's irrelevant packaging problem should not be one.[6]

### D. Completion evidence became too close to a distributed protocol

There is an outer installer, shell batch, observer process, helper, historical marker, per-transition records, refusal records and successful-child observations. Each layer distinguishes its own success from the next layer's success.

Observing a child process's real exit is sensible. The problem is promoting that observation into a persistent prerequisite across later deployment generations, with extensive machinery to handle every publication/observer ordering.

This is a single-host service. The operating system already supervises processes and retains their exit status. A small deployment controller can use systemd supervision, one operation lock, a bounded journal and explicit reconciliation after interruption. It need not manufacture a hierarchy of increasingly qualified success certificates.

No design can make filesystem changes, service startup, application behaviour and a client receiving the final message one atomic transaction. The useful promise is smaller: **observe actual state, retain sufficient recovery information, report uncertainty honestly, and provide a safe reconciliation command.** Do not chase an impossible universal completion proof.[7]

### E. Privacy was implemented partly as diagnostic blindness

The outer process discards live mutation output to `/dev/null`; other boundaries suppress command diagnostics and return broad refusals. Avoiding credentials in chat or log pipes is correct. Deleting the information needed to diagnose a failed start is not the only way to achieve it.

That design made an approved batch fail with little useful explanation, leading to additional administrator prompts—the opposite of the requested one-visit experience.

**Recommendation:** the root-owned controller should retain bounded, access-controlled logs and emit structured nonsecret results: failed phase, unit, exit classification, relevant path, recovery outcome and incident ID. Do not log environment values, tokens, portfolio rows or arbitrary provider errors. Granting read access to a sanitised status file does not require giving the agent general root access.

Protect logs; do not erase observability.[8]

---

## 4. Why so much testing and review did not prevent this

### The tests were often precise about the wrong boundary

The work included genuine real-process and fault-injection tests. It would be unfair to call them all fake. Several reviews found serious bugs, and the eventual cancellation-fixture correction preserved real rollback semantics and was tested against deliberately broken implementations.

But much of the deployment testing substituted ownership, service commands or host responses. That tests controller logic, not whether the final artifact can run under Linux's real access controls and systemd lifecycle.

Repeated examples show the same pattern:

- Fixtures emitted properties that real systemd omitted.
- Fixtures used a different virtual-environment metadata format from the actual package.
- A healthy mock process became `inactive` when stopped, whereas a crashed unit remained `failed`.
- A root/staging-owner import substituted for the actual service account.

**The missing test was not another malformed JSON case. It was a real release rehearsal with the actual artifact, identity, sandbox and failure transition.**

### Independent contexts were not independent assumptions

The parent gave reviewers highly detailed designs and acceptance instructions, often framing each added mechanism as mandatory. Reviewers could find flaws inside that design while still sharing its assumptions and complexity bias.

A useful first reviewer question should have been: **“Why does this ordinary upgrade need this protocol at all?”** That question arrived much later than reviews of individual nonce, marker and timeout behaviours.

### Test volume was repeatedly presented as readiness

“1,503 tests passed” is useful evidence about the suite. It is not a substitute for naming the untested operational boundary. Readiness should be expressed as a matrix of outcomes, not a growing aggregate count.

In this case, “reviewed code; real service-account activation not yet rehearsed” would have been accurate. Calling the material ready for a short operator visit was too optimistic, even when a later sentence mentioned a remaining host gate.

### Agent orchestration amplified a serial problem

The earlier measured window recorded 11 completed agents, 539 model calls and 698 tool calls. Explicit correction tasks consumed 52 minutes, or 30.3% of cumulative completed-agent duration; reviews consumed another 22.0%. Those statistics have an earlier cutoff and exclude later overnight work and the morning incident.

Parallelism helped independent activities, but the central sequence remained implement → reject → repair → review → integrate. Large, tightly prescribed tasks and repeated report/hash/handoff updates added overhead. More agents did not fix the missing architectural decision.

The existing skills also accumulated increasingly specific lessons from each failure. That preserves experience, but can fossilise the accidental architecture: future agents may interpret every incident workaround as a standing product requirement. Keep durable principles; move one-off release pins and protocol history out of general workflow guidance. No skills were changed during this review.[9]

---

## 5. What I would keep

The solution is not to remove safeguards indiscriminately.

Keep:

- Separate web and broker identities and credential boundaries.
- Immutable, root-owned installed releases; no agent edits to live code.
- User review of material product/UI changes and explicit activation approval.
- Exact artifact integrity checks and an expected-current guard.
- Serialized deployments and broker/database writer exclusion.
- A retained previous release and preserved incident records.
- Bounded operations, explicit unknown states and no blind retries.
- No automatic restoration of an old database merely because application startup failed.
- Authentication protections; no public diagnostic bypass containing private data.

However, code approved for production inherits the authority of its service. Root ownership protects against **subsequent unapproved edits**; it does not make approved application code harmless to the credentials or database it legitimately uses. Threat modelling should say that explicitly.

Your refusal to give the agent standing sudo was reasonable. The process should accommodate it, not treat it as the cause of the delay.

---

## 6. Recommended target design

### Stay with native systemd for now

For this single Linux host, I recommend retaining systemd and immutable release directories. Do not introduce Kubernetes, a general deployment platform or a container migration merely to escape this incident. Containers could be a later choice if they simplify reproducibility, but they do not remove database compatibility, permissions, secrets or rollback problems.

### One stable operator tool; one release bundle

The following commands are **illustrative interface proposals, not existing commands to run**:

```
stocks-release prepare <candidate>
stocks-release inspect <release-id>
sudo stocks-release activate <release-id> --expect-current <old-id> --digest <approved-digest>
sudo stocks-release rollback <operation-id>
stocks-release status <operation-id>
```

The initial installation/change of this root-owned tool is a separate administrator-approved maintenance task. Routine releases should not replace the tool.

The tool must not expose arbitrary commands, SQL, hooks, paths or unrestricted sudo. It accepts only a bounded release identifier/digest within the controlled release store. Release code is never executed as root; service-account execution receives only the narrowly intended environment.

A manifest records source revision, artifact digest, runtime requirements, allowed file classes/modes, schema compatibility, health expectations and operator-approved schedule policy. A schema-version range or migration classification replaces a dictionary proving that this particular old/new pair contains exactly the previous session's source files.

### Three phases with a clear maintenance boundary

**Prepare — no production interruption**

Build from an exact source revision in a clean environment. Package only needed runtime files and built UI assets. Produce an explicit mode policy: readable runtime code, executable programs, traversable directories, no secret/state files. Keep build/test material outside the runtime artifact where possible.

**Stage and prove — before stopping the live application**

Copy the approved artifact into a root-controlled release store, verify its digest and modes, and rehearse it as the real service identities with equivalent sandbox restrictions. Use isolated ports, disposable or authorised consistent database copies, synthetic authentication state, no broker credentials, no scheduled jobs and no provider network traffic.

Check imports **and full startup**, assets, a representative read, schema compatibility and a deliberately failed start followed by restoration. A UID change alone is not an equivalent sandbox; mount restrictions, working directory, groups and environment also matter.

A one-time installed, narrowly constrained validation service can make these checks repeatable without asking you to approve arbitrary agent commands. If it is not installed, include these checks at the beginning of the attended batch and describe that limitation honestly. Do not promise zero remaining host uncertainty.

**Activate and verify — short, bounded maintenance**

Acquire the operation lock, check expected current release and compatibility, prevent conflicting writes, record a trusted recovery target, then perform the bounded switch/restart. Run meaningful readiness. On failure, restore the previously proven release through the independent recovery path. Persist one clear operation result.

### Keep proxy and infrastructure outside ordinary app churn

The proxy currently lives under `/opt/stocks/current`, and its unit `Requires=stocks.service`. Stopping the backend therefore stops the public proxy too.

Unless there is a concrete reason to ship Caddy with every application release, separate its executable/configuration lifecycle from app releases. Keep the proxy running during a backend restart and provide a controlled maintenance/unavailable response. This reduces coupled restarts; it is not a promise of zero downtime. Any unit change must be separately tested and approved.[10]

### Make database changes an explicit release class

The application currently runs Alembic `upgrade head` during startup. That is convenient, but makes a restart potentially a database-changing operation. It also means a “readiness rehearsal” is not automatically read-only merely because nobody called an import endpoint.

For production, prefer an explicit migration phase. Classify releases:

- **Code-only:** no schema/data migration; verify old/new schema compatibility and support pointer rollback.
- **Backward-compatible schema:** reviewed migration and tested previous-version compatibility.
- **Destructive or incompatible migration:** separate backup/restore/data-loss decision and maintenance procedure.

A verified SQLite backup is valuable, but automatic database rollback can lose legitimate writes. Never hide that behind the phrase “rolling back is easy.” Application rollback and data restoration are different operations.[11]

### Make scheduler policy independent of web recovery

The worker/timer policy is genuinely important. A `Persistent=true` timer may execute missed work when restarted.

Use one reviewed policy: mutual exclusion with deployments, explicit pause/admission rules, and a defined missed-run outcome. If a catch-up is not approved, leave the worker paused and report it while restoring the website. Do not make uncertainty about the next broker run prevent known-safe web recovery. Retain current broker scope; do not change it as an incidental deployment side effect.

### Define health at the right level

The current protected `/api/health` returns a constant `{"status":"ok"}`; deployment probes mostly prove the unauthenticated `401` boundary. Neither establishes that portfolio queries work.

Use a minimal internal readiness check, reachable only through an appropriately restricted local mechanism, that reports release ID, completed startup and a read-only database/schema check. No portfolio rows or secrets. Keep external authentication-boundary tests as a separate check, then perform one owner-session UI/authentication smoke. Do not weaken public authentication to make deployment verification convenient.[12]

---

## 7. A practical plan, without another uncontrolled rewrite

### First: preserve the stop

Do not automatically resume the interrupted r2 worker. Its uncommitted changes and partial artifact exist, but are not a completed, independently accepted solution. Preserve the incident bundle and existing working release. Do not delete markers to simplify the diagram.

### Next: approve the small design, not another long implementation prompt

Write one short architecture decision covering:

- Threat model and who can change approved code.
- Stable operator boundary and artifact format.
- State transitions and minimum safe rollback conditions.
- Database release classes.
- Actual-identity rehearsal and readiness definition.
- Scheduler and diagnostic policy.

Agree what will be removed or retired as well as what will be added. A replacement that retains all the old layers underneath merely adds another layer.

Moving from the current scheme needs a **one-time, explicitly approved adoption step**: verify the working release and machine configuration, preserve the existing migration/rollback bundles, and establish the simpler controller's baseline. Do not delete the current marker or pretend the old protocol never existed. Once adopted, routine releases should not depend on the entire historical chain remaining a live authorisation mechanism.

### Then: build one complete rehearsal before adding breadth

Demonstrate this vertical slice on a disposable systemd-capable environment matching the Surface:

1. Healthy old release remains available during staging.
2. An unreadable Python dependency is rejected before cutover.
3. A candidate that genuinely crashes after cutover triggers restoration.
4. Recovery handles `failed` with no running process correctly.
5. An interrupted deployment can be inspected and safely reconciled.
6. A broker run cannot overlap the critical transition or occur as an unapproved catch-up.
7. Logs explain failure without exposing credentials or portfolio data.

Only after that works should broader policy/fault coverage expand. Test the exact operator command and artifact, not a specially permissive test-only version of their important boundaries.

### Finally: one controlled deployment opportunity

The acceptance packet should fit on one screen: exact candidate, change summary, schema impact, real rehearsal result, recovery result, remaining manual checks and one command. Preparation happens before your visit. Failure should produce a usable incident result, not another round of blind approval prompts.

No numerical completion-time promise is justified yet. Set and measure an explicit operator-attention budget and recovery objective during the rehearsal; use those measured bounds for the production window.

---

## 8. How future AI work should be managed

1. **Separate feature work from deployment-tool development.** A routine feature release should consume a stable deployment interface.
2. **Review the architecture before delegating large implementations.** Challenge unnecessary state and trust assumptions first.
3. **Give agents outcomes and constraints, not a prescriptive novel of protocol mechanisms.** Over-detailed prompts reproduced the parent's design mistakes.
4. **Use fewer, complementary roles:** one implementer, one adversarial operational reviewer, and a parent responsible for actual acceptance. Add parallel specialists only for genuinely independent work.
5. **After repeated review-driven redesign, stop and reassess.** Do not interpret every new guard as progress.
6. **Maintain one current status record.** Separate archived evidence from current authority; old READY statements must not compete with the latest incident.
7. **Use explicit readiness levels:** code-reviewed; artifact-built; environment-tested; operator-ready; activated; operationally accepted. Never compress them into “done.”
8. **Retain useful tests, not test-count theatre.** Map each major failure risk to an observed acceptance outcome.
9. **Record agent time as engineering overhead.** Optimise time to a verified outcome, not token throughput or parallel-agent count.
10. **Treat user attention as a scarce resource.** Your approval is for a prepared bounded action, not an invitation to begin thinking.

## Bottom line

The route to seamless maintenance is **a smaller stable deployment contract, real service-level rehearsal and simpler recovery**, not more release-specific proof machinery.

The previous work should supply evidence and regression cases for that design. It should not automatically dictate the design itself.

---

## Evidence notes

References are local review snapshots; line numbers refer to the inspected host-v3 code, not the interrupted r2 edits.

1. `/home/geoff/.local/share/stocks-release-ready/prepare_b6_release.py:27–34` — copy/mode policy.
2. `/home/geoff/code/stocks-host-preflight/deploy/upgrade_isolated.py:57–159` — integrity and provenance validation; modes counted directly from the original sealed `stocks-ui-b6b4311.json`.
3. `docs/stocks-release-incident-2026-10-02.md` — observed crash and recovery; exact outage duration was not established.
4. `upgrade_isolated.py:470–590` — historical identity/current-candidate coupling.
5. `upgrade_isolated.py:36–39,124–159`; `upgrade_supervisor.py:21–23`; `operator-host-v3/outer_installer.py:313–333` — release/producer pins embedded in executable code.
6. `upgrade_isolated.py:978–1006,1378–1397` — restoration dependencies and exact inactive requirement.
7. `upgrade_supervisor.py:26–68`; `upgrade_isolated.py:604–643,942–1065` — observation/publication/recovery layers.
8. `operator-host-v3/outer_installer.py:607–712`; `broker_isolation.py:817–826` — output handling and generic failure boundaries.
9. `docs/stocks-maintenance-postmortem-2026-10-01.md` and `stocks-session-analysis-20261001.json` — previously measured, explicitly limited time window. I did not present it as the entire final-session total.
10. `/home/geoff/code/stocks/deploy/stocks-proxy.service:4,18` — proxy dependency and application-relative binary/configuration.
11. `/home/geoff/code/stocks/backend/app/main.py:97–101`; `database.py:29–57` — startup migrations.
12. `main.py:151–153`; `broker_isolation.py:781–801` — application health response and anonymous boundary checks.

Inspected frozen helper SHA256: `5e118d6f93b94bf618b8feb05e30ba83561d8fa4c396da75e8984e7f0fb7d74f`.
Inspected host-v3 outer SHA256: `db17d32107f4467131ba3252f7de19c1d9423c54be328f8e4186560e0117f028`.
Interrupted r2 worktree: `/home/geoff/code/stocks-runtime-access`; uncommitted helper changes plus new test/preparation files, not approved for deployment.

Only this review and its reading-copy/evidence artifacts were produced. No proposed operational change was implemented.
