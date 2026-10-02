#!/usr/bin/python3 -I
"""Fixed nonroot fixture: real uvicorn, disposable SQLite, no broker execution."""
import argparse
import errno
import grp
import json
import os
import pwd
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def check_host_isolation(host_pid_namespace, ipc_canary):
    # Namespace identity and procfs view must both exclude host processes.
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if (not host_pid_namespace or os.readlink('/proc/self/ns/pid') == host_pid_namespace
            or len(status.get('NSpid', '').split()) != 1):
        raise RuntimeError('host-pid-namespace')
    if ipc_canary is None or ipc_canary.parent != Path('/run'):
        raise RuntimeError('missing-host-ipc-canary')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(1)
        try:
            channel.connect(str(ipc_canary))
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise RuntimeError('host-ipc-unknown') from error
        else:
            raise RuntimeError('host-ipc-reachable')
    if any(Path(p).exists() for p in ('/run/dbus/system_bus_socket', '/run/systemd/private', '/run/stocks-agent-ops.sock')):
        raise RuntimeError('host-ipc-visible')
    return {'pid_namespace': os.readlink('/proc/self/ns/pid'),
            'host_pid_namespace': host_pid_namespace, 'host_ipc_canary': 'unreachable'}


def run(release, scratch, actor, broken=False, host_pid_namespace=None, ipc_canary=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise RuntimeError('probe-must-not-run-as-root')
    if sys.version_info[:3] != (3, 14, 4):
        raise RuntimeError('unsupported-runtime')
    if scratch.is_symlink() or scratch.stat().st_uid != os.getuid():
        raise RuntimeError('scratch-owner')
    proof = 'rootless-only'
    isolation = None
    if actor != 'rootless':
        user = pwd.getpwnam(actor)
        if os.getuid() != user.pw_uid or os.getgid() != user.pw_gid:
            raise RuntimeError('actor-mismatch')
        if set(os.getgroups()) != {user.pw_gid, grp.getgrnam('stocks-data').gr_gid}:
            raise RuntimeError('actor-groups')
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        if any(int(status[k].strip(), 16) for k in ('CapEff', 'CapPrm', 'CapBnd', 'CapAmb')) or status['NoNewPrivs'].strip() != '1':
            raise RuntimeError('capabilities')
        interfaces = [line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line]
        if interfaces != ['lo']:
            raise RuntimeError('network-not-isolated')
        isolation = check_host_isolation(host_pid_namespace, ipc_canary)
        proof = 'service-uid-private-network'
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(scratch), 'TMPDIR': str(scratch),
           'PYTHONPATH': str(release / 'backend'), 'PYTHONNOUSERSITE': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
           'PORTFOLIO_DEPLOYMENT_MODE': 'local',
           'PORTFOLIO_DATABASE_URL': 'sqlite+aiosqlite:///' + str(scratch / 'portfolio.db'),
           'PORTFOLIO_AUTH_DATABASE_PATH': str(scratch / 'auth.db'),
           'PORTFOLIO_FRONTEND_DIST': str(release / 'frontend/dist'),
           'PORTFOLIO_SYNC_INBOX': str(scratch / 'inbox'),
           'PORTFOLIO_SYNC_STATUS_DIR': str(scratch / 'status'),
           'PORTFOLIO_SYNC_CONTROL_DIR': str(scratch / 'control'),
           'PORTFOLIO_BROWSER_PROFILE': str(scratch / 'browser'),
           'PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED': 'false',
           'PORTFOLIO_BARCLAYS_AUTOMATION_ENABLED': 'false'}
    module = 'app.__simple_release_missing__:app' if broken else 'app.main:app'
    code = ('import watchfiles,uvicorn; uvicorn.run(' + repr(module) +
            ',host="127.0.0.1",port=18765,workers=1,access_log=False)')
    result = {'status': 'failed', 'uid': os.getuid(), 'gid': os.getgid(),
              'groups': os.getgroups(), 'identity_proof': proof, 'host_isolation': isolation,
              'checks': [], 'python': '3.14.4'}
    child = None
    try:
        with (scratch / 'uvicorn.log').open('xb') as log:
            child = subprocess.Popen([str(release / '.venv/bin/python'), '-B', '-s', '-c', code],
                                     cwd=release, env=env, stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError('startup-exit')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18765/api/portfolio/summary', timeout=2) as response:
                        payload = json.load(response)
                        if response.status != 200 or not isinstance(payload, dict):
                            raise RuntimeError('database-api')
                    break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError('startup-timeout')
            assets = sorted((release / 'frontend/dist/assets').glob('*.js'))
            if not assets:
                raise RuntimeError('missing-asset')
            with urllib.request.urlopen('http://127.0.0.1:18765/assets/' + assets[0].name, timeout=4) as response:
                if response.status != 200 or response.read() != assets[0].read_bytes():
                    raise RuntimeError('asset-content')
            if child.poll() is not None:
                raise RuntimeError('unstable-process')
            result.update(status='passed', checks=['watchfiles', 'lifespan', 'database-api', 'frontend-asset'])
    except Exception as error:  # noqa: BLE001 -- preserve fixture outcome and always clean up
        result['failure'] = type(error).__name__  # no arbitrary app messages
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        (scratch / 'result.json').write_text(json.dumps(result, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--actor', choices=['stocks', 'stocks-sync', 'rootless'], required=True)
    parser.add_argument('--broken', action='store_true')
    parser.add_argument('--host-pid-namespace')
    parser.add_argument('--ipc-canary', type=Path)
    args = parser.parse_args()
    return run(args.release, args.scratch, args.actor, args.broken, args.host_pid_namespace, args.ipc_canary)


if __name__ == '__main__':
    raise SystemExit(main())
