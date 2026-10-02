"""Actual nonroot uvicorn in a network/filesystem namespace, not a service UID claim."""

import json
import os
import subprocess
from pathlib import Path

PROBE = Path(__file__).resolve().parents[1] / 'deploy/simple_release/runtime_probe.py'
RUNTIME = Path('/home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3/release')


def run_probe(tmp_path, broken=False, corrupt=False):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    args = ['/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--unshare-net',
            '--die-with-parent', '--new-session', '--ro-bind', '/usr', '/usr',
            '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib64', '/lib64', '--ro-bind', '/etc/ld.so.cache', '/etc/ld.so.cache',
            '--ro-bind', str(RUNTIME), '/release', '--ro-bind', str(PROBE), '/runtime_probe.py',
            '--bind', str(scratch), '/scratch', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    if corrupt:
        poison = tmp_path / 'watchfiles.py'
        poison.write_text('raise PermissionError("synthetic watchfiles unreadable")\n')
        args += ['--ro-bind', str(poison), '/release/.venv/lib/python3.14/site-packages/watchfiles/__init__.py']
    args += ['--chdir', '/release', '--', '/usr/bin/python3', '-I', '-B', '/runtime_probe.py',
             '--release', '/release', '--scratch', '/scratch', '--actor', 'rootless']
    if broken:
        args += ['--broken']
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=110), scratch


def test_real_nonroot_startup_database_and_asset(tmp_path):
    result, scratch = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((scratch / 'result.json').read_text())
    assert evidence['uid'] == os.getuid() != 0
    assert evidence['python'] == '3.14.4'
    assert evidence['checks'] == ['watchfiles', 'lifespan', 'database-api', 'frontend-asset']
    assert evidence['identity_proof'] == 'rootless-only'
    assert (scratch / 'portfolio.db').stat().st_size > 0


def test_real_corrupt_runtime_fails(tmp_path):
    result, scratch = run_probe(tmp_path, corrupt=True)
    assert result.returncode != 0
    assert 'PermissionError' in (scratch / 'uvicorn.log').read_text()


def test_deliberately_broken_start_is_not_success(tmp_path):
    result, scratch = run_probe(tmp_path, broken=True)
    assert result.returncode != 0
    assert json.loads((scratch / 'result.json').read_text())['status'] == 'failed'
