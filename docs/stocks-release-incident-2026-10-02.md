# Stocks release incident — 2 October 2026 morning

## Outcome

The new release did not remain live. The old release is restored and verified; new release preparation is blocked again. No database restoration was performed. The deployment failure is my responsibility, not a request from Geoff becoming inherently complex.

## Observed timeline

-08:49:58: reviewed host-v3 native batch started; password entry stayed in the system terminal.
-08:54:07: original batch exited1, activation/recovery unconfirmed.
-08:54:34: parent observed new b6 pointer, backend failed with three restarts, proxy dead, worker inactive, timer inactive, TLS unreachable.
-Read-only protected diagnostic: exact artifact/runtime and configuration checks passed, transition activation/preparing in /var/backups/stocks/upgrade-gdrpqxm2. Sanitized startup trace reported PermissionError during uvicorn's watchfiles import.
-Further diagnostic: watchfiles directory0755 but watchfiles/__init__.py0600 root:root. The service identity cannot read that Python source. Full quiescence passed, no service-UID processes remained.
-First explicit unchanged-supervisor rollback exited1 at the stop-confirmation guard.
-Read source: UpgradeSystem.stop accepts only inactive, while systemd retains failed on a stopped failed service. Parent confirmed MainPID0 and quiescence, then used attended administrator approval to reset-failed only stocks.service. This did not start a service, edit a marker or restore data.
-Reviewed supervisor rollback then exited0, restored the old pointer, restarted backend/proxy and restored the safe original timer. Actual helper exit0 was independently observed.
-09:09:43: parent verified old31590ff, backend/proxy active with0 restarts, worker inactive, timer enabled/waiting, anonymous TLS/api/health401.

The site was observed unavailable at08:54:34 and back at09:09:43. The exact outage start is not established by these probes; do not present that interval as an exact total outage duration. HTTP401 is only authentication-boundary evidence, not an owner-session portfolio health check.

## Why the checks missed this

The staging normalizer removed unsafe write permissions but did not add the read permissions required by service accounts. The immutable inventory faithfully sealed an unusable0600 dependency file. Root validation and a geoff-owned staging import could read it, so those checks did not exercise the actual deployed stocks identity.

The failed-state recovery fixture also modelled stopped services as inactive. In reality, systemd can retain a failed state after the process has stopped. The recovery guard rejected that legitimate stopped condition, which delayed restoration. It must not simply accept all failed states: PID/cgroup/quiescence must prove there is no running writer before narrowly clearing the exact stopped unit's failure flag.

Both are basic operating-environment checks that should have existed before activation. Passing many synthetic tests did not compensate for missing the actual execution identity and failed-unit lifecycle.

## Required next candidate

-Do not modify the failed immutable release in place or rerun its attempted batch.
-Create a separate b6-r2 artifact, identical file contents but explicitly reviewed safe runtime readability/traversal modes. Never chmod through interpreter symlinks or expose protected configuration/database files.
-Run a fixed read-only smoke as each required actual service identity in the proposed immutable release before stopping the website. Do not source production credentials or execute lifespan/database initialization for that smoke.
-Test failed stopped states with MainPID/ControlPID/cgroup and existing quiescence checks; normalize only proven-stopped failed units inside explicit recovery, preserving journal/evidence.
-Use the authentic current v3 rollback/observer lineage for the next upgrade. Preserve the original failed artifact, root bundle, attempts and receipts; no marker rewriting or legacy database rollback.
-Complete independent review and freeze the whole new batch before asking Geoff to return.

Source preparation is delegated, not complete evidence: sa-0-ff270a48 / deleg_f3510493. Fresh-session current state is docs/stocks-pickup.md. The previous evening postmortem/statistics retain their stated cutoff and were not rewritten to hide this incident.
