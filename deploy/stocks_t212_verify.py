"""Separate root-only validation gate for the dedicated Trading 212 policy.

Run before/after attended releases and rollback. The original release controller
fingerprint intentionally remains unchanged and does not cover this extension.
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

POLICY = Path('/etc/stocks/t212-policy.json')
FILES = (
    '/etc/systemd/system/stocks-t212-sync.service',
    '/etc/polkit-1/rules.d/49-stocks-t212-sync.rules',
    '/etc/stocks/trading212.env',
    '/usr/local/sbin/stocks-t212-verify',
)


def trusted_file(path):
    path = Path(path)
    for item in (path, *path.parents):
        meta = item.lstat()
        if stat.S_ISLNK(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022:
            raise ValueError('ownership')
    if not path.is_file():
        raise ValueError('file')
    return path.read_bytes()


def verify():
    if os.geteuid() != 0:
        raise ValueError('root-required')
    policy = json.loads(trusted_file(POLICY))
    if set(policy) != {'files', 'worker_sha256'} or set(policy['files']) != set(FILES):
        raise ValueError('policy-schema')
    if POLICY.stat().st_mode & 0o077:
        raise ValueError('private-policy')
    for name, digest in policy['files'].items():
        if hashlib.sha256(trusted_file(name)).hexdigest() != digest:
            raise ValueError('policy-drift')
    if Path('/etc/stocks/trading212.env').stat().st_mode & 0o077:
        raise ValueError('private-environment')
    worker = Path('/opt/stocks/current').resolve() / 'backend/app/trading212_cli.py'
    if hashlib.sha256(trusted_file(worker)).hexdigest() != policy['worker_sha256']:
        raise ValueError('worker-drift')
    result = subprocess.run(
        ['/usr/bin/systemctl', 'show', 'stocks-t212-sync.service', '--property=DropInPaths', '--value'],
        capture_output=True, timeout=10, check=True,
    )
    if result.stdout.strip():
        raise ValueError('unreviewed-drop-ins')
    print('Trading 212 dedicated policy verified')


if __name__ == '__main__':
    try:
        verify()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('Trading 212 policy verification refused', file=sys.stderr)
        raise SystemExit(1)
