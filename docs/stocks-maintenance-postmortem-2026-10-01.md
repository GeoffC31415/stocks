# Stocks maintenance: why a routine release became difficult

Prepared for Geoff. This report describes the 1 October 2026 evening session, not the entire history of the stocks project. Times are British Summer Time. It is based on read-only Hermes session records, exact Git revisions, independent review reports and the actual attended deployment log.

## Executive summary

You asked for routine security/backend improvements to a personal website. The application candidate was already implemented and reviewed. Most of this evening was not spent improving the website: it was spent replacing and repeatedly repairing the machinery used to deploy it.

I made this harder than it needed to be. I treated unfinished deployment engineering as something we could complete while you were briefly available, expanded it into a substantial framework, gave agents inconsistent compatibility assumptions, and declared the batch ready before checking its assumptions against the real host. Independent reviews caught genuine defects, but the review/fix cycle was also evidence of weaknesses in my first-pass work.

The security boundaries themselves were reasonable: no standing agent sudo, protected credentials and production database, root-owned deployed code, and human approval for activation. Those requirements did not imply that you needed to babysit a long release-engineering project.

The actual attended batch refused at preflight. It did not activate the new release. The existing site, inactive sync worker and active daily schedule were verified unchanged. Root-owned staging files and a preactivation receipt were created and retained; saying that absolutely nothing on disk changed would be inaccurate.

## What happened in plain language

### 1. The application was ready, but its release path was not

The approved application commit is b6b43113a6d1be7e40472d27baa22a7c31b8116b. It retains the backend/data/import improvements and preserves the existing production UI rather than deploying the rejected redesign.

Production was running the older release stocks-passkeys-31590ff. It uses separated web and broker service identities, protected configuration/state, and immutable root-owned release directories. The older installer deliberately refuses to operate on that layout. The available isolated-layout upgrader therefore had to be examined before use.

That examination found real defects: its rollback tried to create a marker file that already existed, which could leave the site stopped, and its timer-resume logic did not understand the configuration snapshot it produced. It also had incomplete failure/publication handling. Running that helper unchanged would have been irresponsible.

### 2. I turned repairing that path into a larger deployment project

The original upgrade helper was 147 lines. By the reviewed correction commit it was 1,400 lines, with a 199-line supervisor, a 178-line compatibility module, and a separate 753-line outer installer: 2,530 lines of deployment Python in those four files, before counting tests, the Bash batch and documentation.

Line count is not a quality measure. However, it shows that this was no longer a small finishing task. I should have recognised and communicated the scope change earlier, and chosen a deliberately narrow release procedure rather than allowing complexity to grow through successive reviews.

The extra layers covered immutable artifacts, process completion, failure recovery, service identity, timer safety and approval binding. Several protect useful boundaries, but every new layer creates more interfaces that must agree and more failure modes that must be tested.

### 3. First-pass assumptions were wrong

An early replacement demanded that the entire backend be identical between the old and new releases. That contradicted the purpose of shipping retained backend improvements: the approved pair differed in 15 backend paths.

The relevant compatibility question was whether schema, startup and dependencies remained compatible with restoring the old application version—not whether every backend file was identical. I conflated those two questions in the task framing. The correction had to pin and review the exact allowed delta, reject unrelated changes, and exercise old → new → old startup against disposable data.

Another version treated the entire systemd ExecStart display as static configuration. That display also contains runtime details such as PID, start/stop timestamps and exit status. A normal stop changed the fingerprint, causing both activation and recovery to refuse. Stable command configuration had to be separated from live process identity.

A further failure case showed that a terminal-looking completion record could remain readable after the producing process had actually failed. A separate observer was introduced to record the actual helper-child exit. That observer is not proof that the eventual installer completed; the final outer process still has to be tracked and read back.

### 4. Preparing one approval required another round of integration

To avoid granting the agent general administrator access, the approval command needed to bind exactly the reviewed installer and artifacts. The first wrapper was itself user-writable, so its internal hash checks were not an independent trust anchor. It also read staged files without adequate resource limits and could hang while waiting for a descendant to close an output pipe.

These were corrected with a reviewed literal bootstrap command, bounded streaming reads and bounded process observation. The mutable launcher ceased to be an authority-bearing executable. The helper, observer, compatibility code and outer installer then had to be tested together, rather than only with mocked success at their boundaries.

This explains why separate components could each pass review while the complete operator batch was still not ready.

### 5. The real host exposed assumptions our fixtures had missed

The attended batch started at 22:01:36 and finished with exit 1 at 22:02:23, before activation.

Read-only diagnostics identified two refusals:

- The stored version-2 deployment identity was not identical to a fresh service readback. The comparison covers boot, service invocation and effective configuration. We observed the overall mismatch; the diagnostic did not establish exactly which component differed. The backend was already running since 29 September, so this was not a restart caused by tonight's failed batch.
- This host's systemd 259 omits empty ExecStartPre, ExecStartPost and ExecCondition properties even when queried with --all. The checker expected those keys. Independent typed D-Bus queries proved all nine hook arrays—three hooks across three service units—were actually empty. Missing output is not automatically evidence of empty configuration, but here it could be proved by the independent query.

The tests had modelled complete property responses and matching historical identities. Those assumptions were not true on the Surface. Passing the tests therefore did not establish that the host preflight would accept.

Calling the batch READY before exercising the real, read-only host assumptions was my principal operational mistake. Unsupported host formats were documented as a remaining gate, but that qualification did not make the handoff efficient for you.

## Measured timings and workload

### Scope and method

The measured tree is the CLI session 20261001_191826_d06809 and its direct child sessions in the active default profile. The session began at 19:18:36. Statistics were frozen during the approximately 22:18–22:20 read-only analysis snapshot.

There were 13 sessions in this tree: one main session, 11 completed background agents and one still-running host-correction agent. The running agent is excluded from completed-duration totals. Work before this evening, including earlier UI preservation, is not included in these figures.

Hermes' broader `insights --days 1` output included 16 sessions and approximately $16.27 estimated cost. That broader window includes earlier sessions and is not interchangeable with the narrower tree below.

### Completed background-agent timeline

“Model calls” are recorded LLM API interactions, not calls to a broker. “Tools” are recorded tool calls; nested operations inside a tool are not counted as independent calls here. Durations come from session start/end timestamps and are rounded to the nearest second.

| Start | Work | Duration | Model calls | Tools | Outcome |
|---|---|---:|---:|---:|---|
| 19:20:32 | Initial upgrade safety assessment | 1m 36s | 6 | 19 | Existing upgrader rejected |
| 19:28:47 | First replacement helper | 48m 53s | 145 | 160 | Candidate produced; later review rejected it |
| 20:18:08 | First helper review | 9m 34s | 18 | 31 | Three confirmed blockers |
| 20:19:35 | Outer installer and approval preparation | 16m 09s | 58 | 70 | Candidate produced; later review rejected it |
| 20:28:34 | Correct helper compatibility/config/completion | 37m 36s | 96 | 117 | Corrected candidate produced |
| 20:36:07 | Outer installer review | 4m 20s | 9 | 18 | Three confirmed outer-layer blockers |
| 20:41:09 | Correct outer bounds/approval/process handling | 14m 26s | 95 | 103 | Corrected outer candidate produced |
| 20:55:52 | Outer correction review | 5m 53s | 11 | 20 | Outer mechanisms passed; integration pending |
| 21:06:28 | Corrected helper review | 8m 15s | 13 | 31 | Helper scope passed |
| 21:07:03 | Actual outer/inner integration | 16m 53s | 68 | 88 | Integrated candidate produced |
| 21:24:19 | Final combined review | 8m 12s | 20 | 41 | Conditional approval; host checks still unrun |

Totals for those 11 completed agents:

- Cumulative agent duration: 2h 51m 46s.
- Time with at least one of those agents active: 2h 04m 11s.
- Overlapping work: 47m 35s. This is the difference between cumulative duration and the union of activity intervals, not a proven counterfactual saving against an optimally organised single-worker plan.
- Median agent duration: 9m 34s; longest: 48m 53s.
- 539 recorded model calls and 698 recorded tool calls.

Parallelism helped, but the main dependency chain was largely serial: implement helper → review → repair helper → integrate → final review. Those five agents alone totalled about 2h 01m. Spawning more agents would not eliminate those dependencies.

### Where completed agent effort went

These categories are my classification of the task titles, not Hermes billing categories. They sum cumulative agent time, so parallel activity is intentionally counted for each worker.

| Category | Agents | Cumulative duration | Share |
|---|---:|---:|---:|
| Initial implementation and integration | 3 | 81m 55s | 47.7% |
| Explicit correction/rework | 2 | 52m 02s | 30.3% |
| Diagnosis and independent reviews | 6 | 37m 49s | 22.0% |

The 30.3% rework share is conservative: initial implementation itself included failed tests and iterative corrections. Review time was useful because it found real defects; it should not all be dismissed as bureaucracy. Conversely, passing an independent review does not excuse poor initial assumptions or repeated fixture-only acceptance.

### Tool waiting versus everything between tool calls

I paired each recorded tool request with its result timestamp, then merged overlapping wait intervals inside each child session.

- Recorded tool-await intervals: approximately 57m 00s, or 33.2% of cumulative completed-agent duration.
- Remaining intervals: approximately 1h 54m 47s, or 66.8%.

The remaining time includes model generation, reasoning, request latency, orchestration and unmeasured overhead. The database does not separate those causes, so it would be misleading to label all of it “thinking time.” Tool-await intervals include dispatch/result-recording delay; parallel tool results can be recorded at a common batch boundary. They are not precise CPU timings for individual commands.

The completed children made 214 patch calls, 213 terminal calls, 148 file reads and 37 file writes. There were seven recorded terminal requests invoking the full backend suite; that count includes failed/configuration runs and compound commands, not seven certified distinct successful full-suite executions. Those suites generally took minutes, but test execution alone does not explain the hours.

### Parent and token/cost overhead

At the frozen snapshot, the whole current tree had 692 recorded main-model calls and 908 tool calls. It recorded approximately 73.52 million cumulative token-accounting units, of which 71.44 million—97.2%—were cache-read tokens. It recorded 331,517 output tokens.

Those figures count repeated context processing across model requests, not 73 million unique words or application data. They show that long contexts and many iterative calls were a significant part of the agent workflow. Cache reuse mitigates billing, but does not remove the need to author, review and integrate output.

The tree's recorded estimated main-model cost was about $14.83. No actual billed cost was recorded for these rows. An auxiliary background-review route also recorded about $0.019 in estimates with incomplete cost-status metadata; this is not an invoice. The broad insights window and these scoped estimates should not be added together.

The parent also reread reports, refroze hashes and updated several overlapping handoff documents. Some of that was necessary verification; some was avoidable process churn. The current analytics files preserve the underlying counters so these numbers are auditable rather than guessed.

### Your waiting time versus actual activation time

You first said “Let's go” at 19:20:10. I announced the batch ready at 21:37:24: 2h 17m 14s later.

You returned at 22:01:05. The approximately 23m 41s between the ready announcement and your return is not preparation delay and is not your fault. The actual native batch ran for 47 seconds and refused before activation. A large part of that run was staging and preflight, not website downtime; the website was not stopped by this attempt.

## What was necessary, and what was avoidable

### Necessary

- Do not run a helper with a known broken rollback.
- Protect live credentials and database access; do not solve this by granting general agent sudo.
- Deploy exactly the reviewed application, preserve existing service/drop-in/broker scope, and verify actual output.
- Avoid implicit broker catch-up when restoring a Persistent timer.
- Distinguish successful helper execution, successful installer execution and a verified live application.
- Stop on a failed preflight rather than forcing an activation to satisfy a deadline.

### Avoidable or poorly managed

- Beginning implementation/review only after you arrived to approve commands.
- Describing the application as complete without foregrounding that its deployment mechanism was not production-ready.
- Contradictory compatibility requirements: retain backend changes while requiring backend byte equality.
- Modelling operating-system state with convenient complete fixtures rather than capturing the actual host's read-only output first.
- Reusing a one-off migration identity as the authority for ordinary later upgrades without addressing normal service restarts.
- Allowing a maintenance release to grow into multiple interacting deployment layers without an explicit complexity budget.
- Making repeated readiness claims based on tested code while the host acceptance assumptions remained untested.
- Repeatedly rewriting overlapping handoffs with stale historical READY/RUNNING statements. The morning pickup must be short and authoritative, with history clearly separated.

I do not have evidence that the provider was unusually slow, that your hardware was the dominant bottleneck, or that your lack of a permanent sudo grant caused the delay. The stronger evidence is a long serial engineering/review chain, substantial rework and too many model/tool round trips around an expanding release mechanism.

## Current state and what must happen next

The old site is still live. The reviewed application artifact is prepared. The first attended batch completed with exit 1; it is not a pending prompt and must not be blindly rerun.

The next candidate needs two narrowly reviewed changes:

1. Treat omitted empty systemd hook properties as empty only when the independent typed query actually proves that fact. Query failure, unknown type or a nonempty hook must still refuse.
2. Provide an explicit, tightly bound fresh-baseline approval for this exact old release and captured evidence/current state, rather than editing the old migration marker or falsely presenting its historical identity as current.

The next batch must retain the failed attempt's evidence, use a separate tool/protocol namespace where necessary, and pass independent review and real read-only host-format checks before being described as ready. Privileged activation still needs your attended approval. Authenticated website behaviour still needs an owner session after release; HTTP 401 only proves the login boundary is reachable.

There is no honest guarantee in this report that tomorrow's release will complete in a particular number of minutes. The commitment I can verify is that all agent-owned preparation should be done before requesting your limited operator time, and any remaining blocker should be stated before asking you to sit and wait.

## Morning pickup and evidence

Fresh-session entry point: /home/geoff/code/stocks/docs/stocks-pickup.md
Technical historical handoff: /home/geoff/code/stocks/docs/ui-preservation-handoff.md
Actual attended output-only log: /home/geoff/.local/share/stocks-release-ready/20261001-b6b4311/operator/attended-run-20261001.log
Independent final review: /home/geoff/.local/share/stocks-analysis/isolated-upgrade-final-combined-review-20261001.md
Statistics JSON: /home/geoff/.local/share/stocks-analysis/stocks-session-analysis-20261001.json
Agent timeline CSV: /home/geoff/.local/share/stocks-analysis/stocks-agent-timeline-20261001.csv

This is a measured incident snapshot. The host-correction work was still running when these statistics were collected. Its later completion/review must be added to the pickup file, not silently counted as completed here.
