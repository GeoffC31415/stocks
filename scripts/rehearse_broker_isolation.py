#!/usr/bin/env python3
"""Synthetic, root-only Surface rehearsal; never read or write production state."""
import argparse
import grp
import json
import os
import pwd
import re
import selectors
import signal
import socket
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path

PREFIX = "stocks-isolation-rehearsal-"
PROBE = r'''
import errno, json, os, sqlite3, stat, sys
from pathlib import Path
root, role, action, database, uid, gid, hostns = sys.argv[1:]
root = Path(root)
assert os.getuid() == int(uid) and os.getgid() == int(uid)
assert int(gid) in os.getgroups()
assert os.readlink('/proc/self/ns/mnt') != hostns
assert 'NoNewPrivs:\t1' in Path('/proc/self/status').read_text()
other = 'worker' if role == 'web' else 'web'
def denied(path, mode):
    try:
        with open(path, mode):
            pass
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS), exc
    else:
        raise AssertionError('unexpected access: ' + str(path))
denied(root / other / 'secret', 'rb')
denied(root / 'root-secret', 'rb')
denied(root / 'probe.py', 'ab')
if role == 'worker':
    denied(root / 'web/auth.sqlite3', 'rb')
    (root / 'status/result').write_text('synthetic')
    os.chmod(root / 'status/result', 0o640)
else:
    denied(root / 'worker/broker-input', 'ab')
    denied(root / 'status/result', 'ab')
    assert (root / 'status/result').read_text() == 'synthetic'
(root / role / 'allowed').write_text('synthetic')
db = root / 'shared' / database
connection = sqlite3.connect(db, timeout=5)
connection.execute('PRAGMA busy_timeout=5000')
assert connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
connection.execute('CREATE TABLE IF NOT EXISTS proof (role TEXT)')
connection.execute('INSERT INTO proof VALUES (?)', (role,))
connection.commit()
for suffix in ('', '-wal', '-shm'):
    info = Path(str(db) + suffix).stat()
    assert info.st_gid == int(gid) and stat.S_IMODE(info.st_mode) == 0o660
if action == 'hold':
    print('READY', flush=True)
    assert sys.stdin.readline().strip() == 'CHECK'
assert connection.execute('SELECT COUNT(*) FROM proof').fetchone()[0] == 2
assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print(json.dumps({'identity': True, 'namespace': True, 'denials': True,
                  'wal': True, 'integrity': True, 'rows': 2, 'role': role}), flush=True)
connection.close()
'''


def preflight():
    if os.geteuid() != 0:
        raise RuntimeError("root required; no actions performed")
    if socket.gethostname() != "geoff-Surface-Pro-4":
        raise RuntimeError("wrong host; Surface only")
    if not Path('/run/systemd/system').is_dir():
        raise RuntimeError("systemd system manager required")


def validate_output(path):
    if (not path.is_absolute() or path.parent != Path('/var/tmp')
            or not re.fullmatch(PREFIX + r'[A-Za-z0-9_-]+', path.name)):
        raise RuntimeError("output must be a new /var/tmp/" + PREFIX + " directory")
    if any(p.is_symlink() for p in (path, *path.parents)) or path.exists():
        raise RuntimeError("existing or symlink output refused")


def unused_ids():
    used = {p.pw_uid for p in pwd.getpwall()} | {p.pw_gid for p in pwd.getpwall()}
    used |= {g.gr_gid for g in grp.getgrall()}
    for status in Path('/proc').glob('[0-9]*/status'):
        try:
            for line in status.read_text().splitlines():
                if line.startswith(('Uid:', 'Gid:', 'Groups:')):
                    used.update(map(int, line.split()[1:]))
        except FileNotFoundError:
            pass
    ids = []
    for value in range(60000, 61000):
        if value in used:
            continue
        try:
            pwd.getpwuid(value)
            continue
        except KeyError:
            pass
        try:
            grp.getgrgid(value)
            continue
        except KeyError:
            ids.append(value)
        if len(ids) == 3:
            return tuple(ids)
    raise RuntimeError("no unused numeric identities available")


def layout(ids):
    web, worker, shared = ids
    return {'web': (web, web, 0o700), 'worker': (worker, worker, 0o700),
            'shared': (0, shared, 0o2770), 'status': (worker, web, 0o2750)}


def write(path, text, uid=0, gid=0, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
        os.fchown(stream.fileno(), uid, gid)
        os.fchmod(stream.fileno(), mode)


def fixture(root, ids):
    for name, (uid, gid, mode) in layout(ids).items():
        path = root / name
        path.mkdir(mode=0o700)
        os.chown(path, uid, gid)
        path.chmod(mode)
    for role, uid in zip(('web', 'worker'), ids):
        write(root / role / 'secret', 'synthetic', uid, uid)
    write(root / 'web/auth.sqlite3', 'synthetic', ids[0], ids[0])
    write(root / 'worker/broker-input', 'synthetic', ids[1], ids[1])
    write(root / 'status/result', 'synthetic', ids[1], ids[0], 0o640)
    write(root / 'root-secret', 'synthetic')
    write(root / 'probe.py', PROBE, mode=0o444)
    root.chmod(0o711)  # Traverse only: no listing; child trees enforce privacy.


def command(root, ids, role, unit, action, database):
    if not re.fullmatch(r'stocks-rehearsal-[a-z0-9-]+\.service', unit):
        raise RuntimeError('not an owned rehearsal unit name')
    if role not in ('web', 'worker') or action not in ('hold', 'write'):
        raise RuntimeError('invalid probe')
    uid = ids[0 if role == 'web' else 1]
    other = 'worker' if role == 'web' else 'web'
    properties = [f'User={uid}', f'Group={uid}', f'SupplementaryGroups={ids[2]}',
                  'UMask=0007', 'ProtectSystem=strict', 'ProtectHome=true',
                  'NoNewPrivileges=true', 'PrivateTmp=true', 'PrivateDevices=true',
                  'ProtectKernelTunables=true', 'ProtectKernelModules=true',
                  'ProtectKernelLogs=true', 'ProtectControlGroups=true',
                  'RestrictSUIDSGID=true', 'RestrictRealtime=true', 'LockPersonality=true',
                  'CapabilityBoundingSet=', 'RestrictAddressFamilies=AF_UNIX',
                  'RuntimeMaxSec=45s', 'TimeoutStopSec=5s', 'KillMode=control-group',
                  'TasksMax=16', 'MemoryMax=128M', f'BindReadOnlyPaths={root}',
                  f'ReadWritePaths={root / role} {root / "shared"}' +
                  (f' {root / "status"}' if role == 'worker' else ''),
                  f'ReadOnlyPaths={root / "status"}' if role == 'web' else f'ReadOnlyPaths={root / "probe.py"}',
                  f'InaccessiblePaths={root / other}']
    return ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
            '--unit=' + unit, *['--property=' + p for p in properties],
            '/usr/bin/python3', '-I', '-B', '-u', str(root / 'probe.py'), str(root),
            role, action, database, str(uid), str(ids[2]), os.readlink('/proc/self/ns/mnt')]


def stopped(output):
    values = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    return values.get('ActiveState') in ('inactive', 'failed') and values.get('MainPID') == '0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new /var/tmp/stocks-isolation-rehearsal-NAME directory')
    args = parser.parse_args()
    preflight()
    os.umask(0o077)
    if args.output:
        validate_output(args.output)
        args.output.mkdir(mode=0o700)
        root = args.output
    else:
        if Path('/var/tmp').is_symlink() or Path('/var').is_symlink():
            raise RuntimeError('symlink scratch parent refused')
        root = Path(tempfile.mkdtemp(prefix=PREFIX, dir='/var/tmp'))
    units, children, evidence = [], [], []
    report = {'version': 1, 'passed': False, 'scratch': str(root), 'checks': evidence,
              'sqlite_version': sqlite3.sqlite_version, 'cleanup': False}
    def interrupted(signum, frame):
        raise RuntimeError('interrupted')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        ids = unused_ids()
        report['ids'] = ids
        report['systemd_version'] = subprocess.run(['/usr/bin/systemd-run', '--version'],
            capture_output=True, text=True, check=True, timeout=5).stdout.splitlines()[0]
        fixture(root, ids)
        for index, first in enumerate(('web', 'worker')):
            second = 'worker' if first == 'web' else 'web'
            database = first + '.db'
            names = [f'stocks-rehearsal-{uuid.uuid4().hex}-{index}-{n}.service' for n in range(2)]
            units.append(names[0])
            holder = subprocess.Popen(command(root, ids, first, names[0], 'hold', database),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children.append(holder)
            assert holder.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(holder.stdout, selectors.EVENT_READ)
                if not selector.select(20) or holder.stdout.readline().strip() != 'READY':
                    raise RuntimeError('holder failed readiness; inspect unit journal')
            units.append(names[1])
            writer = subprocess.run(command(root, ids, second, names[1], 'write', database),
                capture_output=True, text=True, timeout=20, check=True)
            evidence.append(json.loads(writer.stdout))
            out, err = holder.communicate('CHECK\n', timeout=15)
            if holder.returncode:
                raise RuntimeError('holder failed: ' + err[-2000:])
            evidence.append(json.loads(out))
        report['passed'] = len(evidence) == 4 and all(
            all(item[key] is True for key in ('identity', 'namespace', 'denials', 'wal', 'integrity'))
            for item in evidence)
    except Exception as exc:  # noqa: BLE001 - preserve diagnostic evidence on every failure
        report['error'] = str(exc)
    finally:
        clean = True
        for unit in units:
            try:
                subprocess.run(['/usr/bin/systemctl', 'stop', unit], capture_output=True, timeout=10, check=False)
                state = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property=ActiveState,MainPID'],
                    capture_output=True, text=True, timeout=5, check=False)
                clean &= state.returncode in (0, 1) and stopped(state.stdout)
            except (OSError, subprocess.SubprocessError):
                clean = False
        for child in children:
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5)
                clean = False
        root.chmod(0o700)
        report['cleanup'] = clean
        report['passed'] &= clean
        write(root / 'report.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
