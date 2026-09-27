# Synthetic broker-isolation rehearsal

**Not yet a privileged acceptance result.** Unit tests validate guards, command
construction, and real unprivileged SQLite database/WAL/SHM modes while open.
They do not establish cross-UID Linux DAC, systemd namespaces, or cross-UID WAL.
Only a reviewed, explicitly approved root execution can fill those gates.

**Replacement startup implemented; independent security review and a newly
approved root run remain mandatory.** The previous 217/USER failure is consistent
with installed systemd 259.5 `systemd.exec(5)`: numeric User/Group IDs absent from
NSS do not satisfy its user-database requirement. No identities are now created.

The transient service starts only fixed `/usr/bin/setpriv` as User=0, Group=0,
with an empty configured SupplementaryGroups list and CapabilityBoundingSet
limited to CAP_SETUID, CAP_SETGID and CAP_SETPCAP. No shell or root Python probe
runs inside the service. The existing root orchestration script is unchanged in
purpose. `setpriv` replaces itself with fixed `/usr/bin/python3 -I -B -u` only
after setting numeric reuid/regid, replacing supplementary groups with exactly
the shared GID, removing all bounding/inheritable/ambient capabilities and
setting no-new-privs. All other sandbox properties and writable paths are retained.

Installed util-linux 2.41.3 `setpriv(1)` documents these flags and fail-closed
option application (exit 127). Its matching upstream `sys-utils/setpriv.c`
sequence retains capabilities while changing UID, restores effective capabilities,
sets GIDs/groups, drops bounding then inheritable/ambient sets, and execs.
CAP_SETPCAP is needed for the bounding-set drop; UID change alone is not the
capability drop. Executing the ordinary nonprivileged interpreter with nonzero
UIDs and empty bounding/inheritable/ambient sets removes permitted/effective
capabilities; the probe verifies the result before any attempted writes.

**Trusted-OS prerequisite:** the packaged setpriv and Python executables, their
symlink targets, every ancestor directory, dynamic loader/libraries, Python
standard library and system-manager environment must be root-controlled and not
writable by untrusted users. `/usr/bin/python3` may legitimately be a packaged
symlink; this script does not add an incomplete symlink-rejecting trust check.
The installed system manager and its initial credentials are trusted. An empty
SupplementaryGroups assignment resets the configured list, not arbitrary inherited
groups (systemd 259 skips NSS group initialization for GID 0); exact singleton
groups are enforced by setpriv and checked in the Python probe. Independent review
must confirm this prerequisite before privileged execution. No replacement root
run has been performed or accepted.

Readiness failures now snapshot at most 2000 available stderr bytes from the
synthetic child before cleanup, without waiting for stderr or changing its final
blocking mode. This is a diagnostic snapshot, not a complete journal; unavailable
stderr is explicitly reported. Privileged startup failures can still require the
unit journal. No automatic retry is performed.

Historical invocation only — **do not run until startup is fixed, independently
reviewed, and a new root execution is explicitly approved** on
`geoff-Surface-Pro-4`:

```sh
sudo /usr/bin/python3 -I /home/geoff/code/stocks-root-rehearsal/scripts/rehearse_broker_isolation.py
```

No arguments are required. Optional `--output` must name a **nonexistent** direct
child of `/var/tmp` named `stocks-isolation-rehearsal-NAME` (letters, digits,
underscore and hyphen only). Existing paths and symlink ancestors are refused.

The script creates synthetic markers and SQLite databases only in its exclusive
scratch directory. It does not import the app, read environment files, access live
portfolio state, contact providers, create accounts/groups, install units, or
stop/restart live services. It chooses three numeric IDs absent from NSS and the
current process UID/GID/group snapshot; this is not an account reservation, so do
not concurrently allocate users in the 60000–60999 range during this short run.

Root-owned scratch is initially 0700, temporarily 0711 solely for traversal;
private web/worker subtrees are 0700. Shared data is root:shared 2770, databases
and live WAL/SHM files must be 0660. The holding probe exclusively precreates its
empty database (O_EXCL/O_NOFOLLOW, descriptor-based chmod 0660) before SQLite
opens it, retaining creator UID and setgid-inherited GID. UMask=0007 alone would
leave SQLite's default 0644 creation at 0640. Both connections use mode=rw, so
the second writer cannot silently create a missing database. This mirrors the
production database's explicit 0660 initialization; no production permissions
or migration code are changed. Status is worker:web 2750 with a 0640 file.
The root-owned probe is 0444. The whole evidence tree returns to 0700 afterward.

Four uniquely named transient systemd services use distinct numeric identities,
shared supplementary group, bounded runtime, control-group cleanup, strict
filesystem protection and the candidate isolation sandbox properties. PrivateTmp
is retained; an explicit scratch bind makes only this fixture visible through it.
Address families are narrowed to AF_UNIX (unlike networked production workers).
Read/write and inaccessible paths map to scratch; no StateDirectory is requested.

Before any attempted write, each probe checks all four real/effective/saved/fs
UID and GID fields, exactly the singleton shared supplementary group, zero
CapInh/CapPrm/CapEff/CapBnd/CapAmb and NoNewPrivs=1 from `/proc/self/status`.
Acceptance explicitly requires `capabilities: true` in every probe record.
It also checks a different mount namespace from its parent,
denied opposite-private/secret/code access, permitted own-private
writes, and status/broker-input/auth boundaries. Both web-first and worker-first
SQLite WAL creation are tested: the first connection stays open while the other
identity commits. Both connections verify exactly two rows and integrity `ok`;
sidecars are inspected while live, not after SQLite deletes them.

Success requires exit 0 and JSON `passed: true`, four successful probe records,
and `cleanup: true`. JSON is printed and saved as `report.json` under the reported
scratch path. All scratch evidence is retained on success **and failure**; no
recursive deletion is performed. Cleanup stops only generated rehearsal unit
names, checks inactive/failed state and MainPID=0, and reaps child processes.
A failed run is not approval to modify production permissions. Review its report
and the journals for the uniquely named `stocks-rehearsal-*` units. The script
requires systemd features to work; it never silently falls back to a weaker probe.

Nonprivileged verification (no sudo/systemd commands are executed by these tests):

```sh
cd /home/geoff/code/stocks-root-rehearsal
PYTHON_DOTENV_DISABLED=1 PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: /home/geoff/code/stocks/.venv/bin/python -m pytest tests/test_rehearse_broker_isolation.py -q
/home/geoff/code/stocks/.venv/bin/ruff check scripts/rehearse_broker_isolation.py tests/test_rehearse_broker_isolation.py
```
