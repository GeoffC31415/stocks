# Stocks pickup — LIVE on the simple release workflow

## Current outcome

Approved application b6b43113a6d1be7e40472d27baa22a7c31b8116b is LIVE.
Parent verified at2026-10-02 12:26BST: exact new pointer, all3768 regular-file hashes/root modes against frozen manifest, backend/proxy active withzero restarts, workerinactive, timeractive/enabled waiting. Original daily18:30Europe/London policy and2min random delay preserved; LastTrigger unchanged. TLS/api/health401 proves only auth boundary. Owner confirmed via the acceptance prompt: “Sign-in and portfolio look correct.” This closes the requested owner-session acceptance; it does not claim exhaustive testing of every authentication/recovery feature.

Managed deployment: stocks-release-operation-20261002-r3b.service
Invocation:99c9bef5bec3494d85a18192be3ced36
Original result:success, exited0; runtime63.101s.
Controller operation:a13a2249bb6c4d09b421ff56c0ae45b5, status deployed, timer_restoredtrue.
Private log:/var/lib/stocks-release/operation-1a9324ea3ae54f0b8d6270ee862e2519.log
State:/var/lib/stocks-release/state.json

## Installed workflow and source

Stable CLI:/usr/local/sbin/stocks-release
Root code:/usr/local/lib/stocks-release
Controller SHA256:916b178dd37d8ed9be49aace4f13a2c8080adf52b2ba7322a9d8b82687ed5bd6
Probe SHA256:8e2b3e683963bbe124687919cf92052dd5e757eb94e87736bf3e3d04c0c0cefa
Installed/source bytes checked identical. Real native stocks/stocks-sync isolation/startup/DBAPI/asset checks and root0600 deliberatefailure/healthyrestoration all passed before cutover. Native rehearsal log:/var/lib/stocks-release/operation-c3bf5cce2c5f46ea8a0c7e5897c301d6.log

Live:/opt/stocks/simple-releases/4c9c2d60bf202c524fbfb7874ec279ffd8acb174794e5789720dc3e1e250180b
Previous known good:/opt/stocks/releases/stocks-passkeys-31590ff
Bundle:/home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3
Manifest SHA256:4c9c2d60bf202c524fbfb7874ec279ffd8acb174794e5789720dc3e1e250180b

All three simple-workflow source commits were selectively cherry-picked into main /home/geoff/code/stocks (no legacy deployment rewrite brought across). Tool implementation integration HEAD:abde1af0a1be6648681185aaced4215f56315a47; application/dependencies/units remain identical to approvedb6. Original development worktree /home/geoff/code/stocks-simple-release at69682516cf479bd1943a84bca1d5b62e5251db1e. Focused suite rerun after integration:65passed12.46s. No remote push requested/performed. Main checkout has unrelated pre-existing dirty/untracked work; never reset/clean/stage broadly.

## Future operation

Use docs/simple-release.md and deploy/simple_release/. Do not rerun one-time install or adopt on this existing installation. Future code-only releases: prepare a new manifest/bundle, inspect, approve its digest, then use installed deploy with the ACTUALLY observed current target. A stable tool and release data replace the obsolete host-v3 chains. Schema/auth/unit configuration changes need their own reviewed procedure; do not bypass code-only guards.

Installed status: sudo /usr/local/sbin/stocks-release status
Recovery is explicit through installed rollback with exact operationID and observed current pointer (see runbook). Do not invoke legacy upgrade/migration rollback or restore oldDBdata. Retain protected incident/evidence/old artifacts; no clean-up authorisation is implied. Root-installed code must remain non-agent-writable; no standing sudo or credential exposure.

Geoff is available daytime, not dependably after18:00. Complete preparation/review before brief attended actions. No task agents are running; do not start new work merely to continue an old status report.

## Resolved attempt before successful release

First simple managed operation941cceb55dc04f8db6699b6ad3b6770f returnedattention, restoringoldpointer but treating very earlyType=simple cwd/exe observations as fatal. Later strictoldreadback passed. Parent explicitly verifiedold/policy/runtime underlocks, safely restoredtimer within originalwindow and recordedoperator-readback restoration. Exact identityfield that was transient was not recorded; do not invent it. Narrow reviewed correction retries initialcwd/exe checks within existing60s startupdeadline, never accepts mismatching finalidentity, starts units onlyonce and preserves safe failure reasons. Installed oldcontroller retained as root backup. Successfulnewoperation above supersedes that attempt operationally, not historically.

Earlier legacy morningoutage is documented separately and its bundle /var/backups/stocks/upgrade-gdrpqxm2 remains preserved. Interruptedr2 worktree remains abandoned partial work, not deployed. Do not resume it.

## Evidence and reports

Runbook:docs/simple-release.md
Architecture review:docs/astra-design-review-2026-10-02.md
Prior incident:docs/stocks-release-incident-2026-10-02.md
Frozen earlier session report:docs/stocks-maintenance-postmortem-2026-10-01.md
Previous pickup history:docs/stocks-pickup-pre-simple-live-20261002.md
Independent approvals under /home/geoff/.local/share/stocks-analysis/:
 simple-release-operational-review-refresh-20261002.md
 simple-release-startup-review-20261002.md
Installation/rehearsal terminal log:simple-install-rehearse-20261002-121402.log

Owner-session acceptance is confirmed as recorded above. Future releases still require actual owner acceptance rather than treating401 as a UI pass. This task has no remaining deployment or approval action; unrelated broker/backlog work is outside this closure.
