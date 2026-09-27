# Synthetic broker-isolation rehearsal

**Not yet a privileged acceptance result.** Unit tests validate guards and command
construction, not Linux DAC, systemd namespace support, or cross-UID WAL behavior.
Only a reviewed, explicitly approved root execution can fill those gates.

On `geoff-Surface-Pro-4`, after reviewing this script:

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
and live WAL/SHM files must be 0660. Status is worker:web 2750 with a 0640 file.
The root-owned probe is 0444. The whole evidence tree returns to 0700 afterward.

Four uniquely named transient systemd services use distinct numeric identities,
shared supplementary group, bounded runtime, control-group cleanup, strict
filesystem protection and the candidate isolation sandbox properties. PrivateTmp
is retained; an explicit scratch bind makes only this fixture visible through it.
Address families are narrowed to AF_UNIX (unlike networked production workers).
Read/write and inaccessible paths map to scratch; no StateDirectory is requested.

Each probe checks actual UID/group, a different mount namespace from its parent,
NoNewPrivileges, denied opposite-private/secret/code access, permitted own-private
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
