#!/usr/bin/python3 -I
"""Stocks code-only release controller. Standard library; never imports app code."""
# ruff: noqa: BLE001 -- any operational error must reach compensation/diagnosis
import ast
import contextlib
import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import stat
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

PROCESS_KEYS = ('ActiveState', 'MainPID', 'ControlPID', 'ControlGroup')
TIMER_KEYS = ('ActiveState', 'UnitFileState', 'Persistent', 'NextElapseUSecRealtime',
              'RandomizedDelayUSec', 'TimersCalendar')


def schedule_window(props, now):
    if (props.get('ActiveState') != 'active' or props.get('UnitFileState') != 'enabled'
            or props.get('Persistent') != 'yes' or props.get('RandomizedDelayUSec') != '2min'):
        raise Refused('schedule-policy')
    match = re.fullmatch(r'\{ OnCalendar=\*-\*-\* 18:30:00 Europe/London ; next_elapse=@(\d+) \}', props.get('TimersCalendar', ''))
    if not match or not re.fullmatch(r'@\d+', props.get('NextElapseUSecRealtime', '')):
        raise Refused('schedule-format')
    earliest = min(int(match[1]), int(props['NextElapseUSecRealtime'][1:]) - 120)
    deadline = earliest - 60
    if now + 300 >= deadline:
        raise Refused('schedule-window')
    return {'deadline': min(deadline, now + 300), 'started_wall': now, 'started_mono': time.monotonic(),
            'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'enabled': 'enabled'}


COMPAT_FILES = ('backend/app/main.py', 'backend/app/database.py', 'backend/app/models.py',
    'backend/app/config.py', 'backend/app/passkeys.py', 'backend/app/security.py',
    'alembic.ini', 'requirements-production.txt', 'deploy/Caddyfile')


def compatibility(rows):
    files = {r['path']: r['sha256'] for r in rows if r['type'] == 'file'}
    if any(p not in files for p in COMPAT_FILES):
        raise Refused('missing-compatibility-input')
    selected = {p: h for p, h in files.items() if p in COMPAT_FILES or p.startswith('backend/alembic/')}
    if not any(p.startswith('backend/alembic/versions/') for p in selected):
        raise Refused('missing-migrations')
    return sha(encoded(selected))


def permissions(root, owner=0, rows=None):
    paths = [root / r['path'] for r in rows] if rows is not None else list(root.rglob('*'))
    for p in [root, *paths]:
        info = p.lstat()
        if info.st_uid != owner:
            raise Refused('runtime-owner')
        if stat.S_ISLNK(info.st_mode):
            if LINKS.get(p.relative_to(root).as_posix()) != os.readlink(p):
                raise Refused('link')
            continue
        required = 0o555 if p.is_dir() or p == root / 'bin/caddy' else 0o444
        if info.st_mode & 0o022 or info.st_mode & required != required or info.st_mode & 0o7000:
            raise Refused('runtime-permission')
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise Refused('file-type')


def lock_contract(root):
    bodies = []
    for filename, function in [('backend/app/sync_cli.py', '_run'),
                               ('backend/app/services/sync_control.py', 'file_lock')]:
        tree = ast.parse(read_regular(root, filename))
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function]
        if len(nodes) != 1:
            raise Refused('lock-contract')
        bodies.append(ast.dump(ast.Module(body=nodes[0].body, type_ignores=[])))
    # Body comparison ignores annotations/comments only, not operations.
    if "value='sync-run.lock'" not in bodies[0] or "attr='flock'" not in bodies[1]:
        raise Refused('lock-contract')
    return sha(encoded(bodies))


def stable_exec(value):
    m = re.fullmatch(r'\{ path=(.*?) ; argv\[\]=(.*?) ; ignore_errors=(no|yes) ; .* \}', value)
    if not m or ' ; ' in m[1] or ' ; ' in m[2]:
        raise Refused('exec-format')
    return list(m.groups())


def private_config():
    # Called only by installed root controller, never during development/tests.
    hashes = {}
    for name in ('production.env','brokers.env','caddy.env'):
        path = Path('/etc/stocks') / name
        info = path.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
            raise Refused('private-config-owner')
        data = read_regular(path.parent, path.name, 65536)
        hashes[name] = sha(data)
        if name == 'brokers.env':
            for line in data.decode().splitlines():
                if line.startswith('PORTFOLIO_SYNC_INBOX='):
                    values = shlex.split(line.split('=',1)[1])
                    if values != [str(SYNC_LOCK.parent)]:
                        raise Refused('sync-inbox-override')
    return sha(encoded(hashes))


class NativeHost:
    def __init__(self, log):
        self.log = Path(log)

    def run(self, argv, timeout=55, allow_failure=False):
        # Commands are fixed internally. Never invoke manifest paths as root code.
        self.unit = next((a for a in argv if a in UNITS or re.fullmatch(r'stocks-release-probe-[a-f0-9]+\.service', a)), None)
        try:
            result = subprocess.run(argv, check=False, env={'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C'},
                                    capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            result = subprocess.CompletedProcess(argv, 124, error.stdout or b'', error.stderr or b'')
        with self.log.open('ab') as log:
            os.fchmod(log.fileno(), 0o600)
            remaining = max(0, 8 * 1024 * 1024 - log.tell())
            entry = encoded({'command': argv, 'returncode': result.returncode}) + result.stdout[:512000] + result.stderr[:512000]
            log.write(entry[:remaining])
        if result.returncode and not allow_failure:
            raise Refused('host-command-failed')
        return result.stdout.decode('utf-8', errors='replace')

    def fingerprint(self):
        return sha(encoded([self.public_policy(), private_config(),
                            sha(Path('/usr/bin/python3').read_bytes())]))

    def rehearse(self, release):
        self.probe_once(release, 'stocks')
        self.probe_once(release, 'stocks-sync')
        fixture = STATE / 'rehearsal' / ('recovery-' + uuid.uuid4().hex)
        fixture.mkdir(mode=0o755)
        fixture.chmod(0o755)
        bad = fixture / 'broken'
        copy_rows(release, bad, inventory(release, runtime=True))
        (bad / '.venv/lib/python3.14/site-packages/watchfiles/__init__.py').chmod(0o600)
        pointer = fixture / 'current'
        atomic_pointer(pointer, release)
        atomic_pointer(pointer, bad)
        # Only this disposable pointer moves. The real failed unit must be cleared
        # using PID/cgroup proof before restoring and starting the healthy fixture.
        self.probe_once(pointer, 'stocks', broken=True)
        atomic_pointer(pointer, release)
        self.probe_once(pointer, 'stocks')
        return {'fixture_pointer': str(pointer)}

    def probe_once(self, release, actor, broken=False):
        nonce = uuid.uuid4().hex
        scratch = STATE / 'rehearsal' / nonce
        scratch.mkdir(mode=0o700)
        user = pwd.getpwnam(actor)
        os.chown(scratch, user.pw_uid, user.pw_gid)
        unit = 'stocks-release-probe-' + nonce + '.service'
        command = rehearsal_command(release, scratch, actor, nonce)
        failed = False
        try:
            self.run(command, timeout=115)
        except Refused:
            failed = True
        finally:
            self.run(['/usr/bin/journalctl', '--no-pager', '--unit', unit, '--lines=150'], allow_failure=True)
        props = self.show(unit, (*PROCESS_KEYS, 'Result', 'ExecMainStatus'))
        if broken:
            if not failed or props['ActiveState'] != 'failed' or props['Result'] != 'exit-code' or props['ExecMainStatus'] != '1':
                raise Refused('broken-rehearsal-not-failed')
            if b'PermissionError' not in read_regular(scratch, 'uvicorn.log', 1024 * 1024):
                raise Refused('broken-rehearsal-wrong-failure')
            self.stop_unit(unit)  # actual zero PID/cgroup proof before exact reset-failed
        else:
            if failed or props['Result'] != 'success' or props['ExecMainStatus'] != '0':
                raise Refused('rehearsal-failed')
            if props['MainPID'] != '0' or props['ControlPID'] != '0' or self.populated(unit, props):
                raise Refused('probe-process-survived')
            self.run(['/usr/bin/systemctl', 'stop', unit])
        # Probe bytes are evidence, never root code or instructions.
        result = json.loads(read_regular(scratch, 'result.json', 65536))
        expected = 'failed' if broken else 'passed'
        if result.get('status') != expected or result.get('uid') != user.pw_uid:
            raise Refused('probe-result')

    def public_policy(self):
        policy = {}
        for unit in UNITS:
            keys = ['NeedDaemonReload', 'FragmentPath', 'DropInPaths', 'UnitFileState']
            if unit.endswith('.service'):
                keys += ['ExecStart', 'User', 'Group', 'SupplementaryGroups', 'WorkingDirectory',
                         'Environment', 'EnvironmentFiles', 'ProtectSystem', 'ProtectHome', 'NoNewPrivileges']
            p = self.show(unit, keys)
            if p['NeedDaemonReload'] != 'no':
                raise Refused('daemon-reload-pending')
            if unit.endswith('.service'):
                p['ExecStart'] = stable_exec(p['ExecStart'])
                if p['ProtectSystem'] != 'strict' or p['ProtectHome'] != 'yes' or p['NoNewPrivileges'] != 'yes':
                    raise Refused('unit-sandbox')
                bus = '/org/freedesktop/systemd1/unit/' + unit.replace('-', '_2d').replace('.', '_2e')
                for hook in ('ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost'):
                    # systemctl omits empty arrays; do not turn absent into empty.
                    value = self.run(['/usr/bin/busctl', 'get-property', 'org.freedesktop.systemd1',
                                     bus, 'org.freedesktop.systemd1.Service', hook]).strip()
                    if value != 'a(sasbttttuii) 0':
                        raise Refused('unit-hook')
            p['unit_text_hash'] = sha(self.run(['/usr/bin/systemctl', 'cat', unit]).encode())
            policy[unit] = p
        for unit, actor in [('stocks.service','stocks'), ('stocks-sync.service','stocks-sync')]:
            p = policy[unit]
            if p['User'] != actor or p['Group'] != actor or p['SupplementaryGroups'] != 'stocks-data' or p['WorkingDirectory'] != '/opt/stocks/current':
                raise Refused('unit-identity')
        worker = policy['stocks-sync.service']
        if worker['ExecStart'] != ['/opt/stocks/current/.venv/bin/python', '/opt/stocks/current/.venv/bin/python -m app.sync_cli --only barclays', 'no']:
            raise Refused('worker-command')
        env = dict(item.split('=', 1) for item in shlex.split(worker['Environment']))
        if env.get('PORTFOLIO_SYNC_INBOX') != str(SYNC_LOCK.parent):
            raise Refused('sync-lock-path')
        for unit, filename in [('stocks.service','production.env'), ('stocks-sync.service','brokers.env'), ('stocks-proxy.service','caddy.env')]:
            if policy[unit]['EnvironmentFiles'] != f'/etc/stocks/{filename} (ignore_errors=no)':
                raise Refused('environment-file-policy')
        return policy

    def validate(self, target):
        target = Path(target)
        if target.parent not in (STORE, Path('/opt/stocks/releases')) or not re.fullmatch('[A-Za-z0-9_-]+', target.name) or target.is_symlink():
            raise Refused('release-location')
        for p in [target.parent, *target.parent.parents]:
            info = p.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise Refused('release-parent')
        rows = inventory(target, runtime=True)
        permissions(target, rows=rows)
        for name in ('.venv/bin/python','bin/caddy','frontend/dist/index.html'):
            if not (target / name).is_file():
                raise Refused('missing-runtime')
        if not (target / 'bin/caddy').stat().st_mode & 0o111:
            raise Refused('caddy-not-executable')
        return {'path':str(target), 'inventory':sha(encoded(rows)),
                'compat':sha(encoded([compatibility(rows), lock_contract(target)]))}

    def verify_web(self, target):
        identities = []
        for unit in UNITS[:2]:
            p = self.show(unit, ('ActiveState','MainPID','ControlPID','NRestarts'))
            if p['ActiveState'] != 'active' or p['NRestarts'] != '0' or p['ControlPID'] != '0' or int(p['MainPID']) <= 0:
                raise Refused('web-not-stable')
            proc = Path('/proc') / p['MainPID']
            if unit == 'stocks.service':
                if (proc / 'cwd').resolve() != target:
                    raise Refused('web-release-mismatch')
                expected_exe = Path('/usr/bin/python3').resolve()
            else:
                expected_exe = target / 'bin/caddy'
            if (proc / 'exe').resolve() != expected_exe:
                raise Refused('web-executable-mismatch')
            identities.append(p)
        # This is ONLY an anonymous authentication boundary, not owner health.
        code = self.run(['/usr/bin/curl', '--silent', '--show-error', '--max-time','8',
                         '--noproxy','*','--resolve','solarpi.hopto.org:5000:127.0.0.1',
                         '--output','/dev/null','--write-out','%{http_code}',
                         'https://solarpi.hopto.org:5000/api/health'])
        if code.strip() != '401':
            raise Refused('https-auth-boundary')
        for unit, expected in zip(UNITS[:2], identities):
            if self.show(unit, ('ActiveState','MainPID','ControlPID','NRestarts')) != expected:
                raise Refused('web-identity-changed')

    def start_web(self, target):
        for unit in UNITS[:2]:
            self.run(['/usr/bin/systemctl','start',unit])
        time.sleep(3)
        self.verify_web(target)

    def show(self, unit, keys):
        text = self.run(['/usr/bin/systemctl', 'show', '--timestamp=unix', unit,
                         *['--property=' + k for k in keys]])
        props = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        if any(k not in props for k in keys):
            raise Refused('missing-unit-property')
        return props

    def populated(self, unit, props):
        group = props['ControlGroup']
        if not group:
            return False
        if not group.startswith('/system.slice/') or '..' in group:
            raise Refused('cgroup-path')
        root = Path('/sys/fs/cgroup') / group.lstrip('/')
        if not root.exists():
            return False
        files = list(root.rglob('cgroup.procs'))
        if not files:
            raise Refused('cgroup-unknown')
        return any(p.read_text().strip() for p in files)

    def quiescent(self, unit):
        p = self.show(unit, PROCESS_KEYS)
        if not stopped(p, bool(self.populated(unit, p))):
            raise Refused('not-stopped')
        return p

    def stop_unit(self, unit):
        self.run(['/usr/bin/systemctl', 'stop', unit])
        props = self.quiescent(unit)
        if props['ActiveState'] == 'failed':
            self.run(['/usr/bin/systemctl', 'reset-failed', unit])
            if self.show(unit, ('LoadState',)).get('LoadState') != 'not-found':
                self.quiescent(unit)

    def before_pause(self):
        self.quiescent('stocks-sync.service')
        for unit in UNITS[:2]:
            p = self.show(unit, ('ActiveState', 'MainPID', 'NRestarts'))
            if p['ActiveState'] != 'active' or int(p['MainPID']) <= 0 or p['NRestarts'] != '0':
                raise Refused('web-not-stable')
        return schedule_window(self.show('stocks-sync.timer', TIMER_KEYS), time.time())

    def pause(self):
        self.quiescent('stocks-sync.service')
        self.run(['/usr/bin/systemctl', 'stop', 'stocks-sync.timer'])
        self.quiescent('stocks-sync.service')
        if self.show('stocks-sync.timer', ('ActiveState',))['ActiveState'] != 'inactive':
            raise Refused('timer-not-paused')

    def stop_web(self):
        self.quiescent('stocks-sync.service')
        for unit in ('stocks-proxy.service', 'stocks.service'):
            self.stop_unit(unit)

    def restore_timer(self, saved):
        wall, mono = time.time(), time.monotonic()
        if (Path('/proc/sys/kernel/random/boot_id').read_text().strip() != saved['boot']
                or wall >= saved['deadline'] or wall < saved['started_wall']
                or abs((wall - saved['started_wall']) - (mono - saved['started_mono'])) > 5):
            return False
        self.quiescent('stocks-sync.service')
        if self.show('stocks-sync.timer', ('UnitFileState',))['UnitFileState'] != saved['enabled']:
            return False
        self.run(['/usr/bin/systemctl', 'start', 'stocks-sync.timer'])
        return self.show('stocks-sync.timer', ('ActiveState',))['ActiveState'] == 'active'



def atomic_pointer(pointer, target):
    tmp = pointer.with_name('.simple-current-' + uuid.uuid4().hex)
    tmp.symlink_to(target)
    os.replace(tmp, pointer)
    sync_dir(pointer.parent)


def durable_json(path, value):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(encoded(value))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    sync_dir(path.parent)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def locked(path, existing=False):
    # Keep the inode: this is also the existing app's sync-run.lock convention.
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (0 if existing else os.O_CREAT), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refused('lock-type')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused('busy') from None
        yield
    finally:
        os.close(fd)


class Controller:
    """One state record, one operation lock; host adapter owns fixed system scope."""
    def __init__(self, state, pointer, sync_lock, host):
        self.root, self.pointer, self.sync_lock, self.host = Path(state), Path(pointer), Path(sync_lock), host
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.record = self.root / 'state.json'

    def status(self):
        return json.loads(self.record.read_bytes()) if self.record.exists() else {'status': 'not-adopted'}

    def save(self, state):
        durable_json(self.record, state)

    def current(self):
        return os.readlink(self.pointer)

    def switch(self, target):
        atomic_pointer(self.pointer, target)

    def adopt(self, expected):
        with locked(self.root / 'operation.lock'):
            if self.record.exists():
                raise Refused('already-adopted')
            if self.current() != expected:
                raise Refused('current-mismatch')
            old = self.host.validate(Path(expected))
            policy = self.host.fingerprint()
            self.host.before_pause()  # observation only, no scheduler/service change
            self.host.verify_web(Path(expected))
            state = {'current': old, 'previous': old, 'policy': policy, 'operation': None}
            self.save(state)
            return state

    def preflight(self, state, expected):
        if self.current() != expected or state['current']['path'] != expected:
            raise Refused('current-mismatch')
        if self.host.fingerprint() != state['policy']:
            raise Refused('policy-drift')
        if state['operation'] and state['operation']['status'] in ('running', 'attention'):
            raise Refused('interrupted-status-before-retry')
        if self.host.validate(Path(expected)) != state['current']:
            raise Refused('current-changed')
        self.host.verify_web(Path(expected))

    def phase(self, state, name):
        state['operation']['phase'] = name
        self.save(state)

    def restore(self, state):
        op = state['operation']
        old = op['recovery']
        # Deliberately no candidate reads. Recovery authority was saved before cutover.
        if self.host.validate(Path(old['path'])) != old:
            raise Refused('recovery-changed')
        self.phase(state, 'restore-web')
        self.host.stop_web()
        self.switch(Path(old['path']))
        self.host.start_web(Path(old['path']))
        state['current'] = old
        op['status'] = 'restored'

    def finish_timer(self, state):
        op = state['operation']
        try:
            op['timer_restored'] = self.host.restore_timer(op['schedule'])
        except Exception:
            op['timer_restored'] = False
        if not op['timer_restored']:
            op['status'] = 'attention'
        self.save(state)

    def rollback(self, operation_id, expected):
        with locked(self.root / 'operation.lock'), locked(self.sync_lock, existing=True):
            state = self.status()
            op = state['operation']
            if not op or op['id'] != operation_id or self.current() != expected:
                raise Refused('recovery-expectation')
            if expected not in (op['candidate']['path'], op['recovery']['path']):
                raise Refused('unknown-pointer')
            if self.host.fingerprint() != state['policy']:
                raise Refused('policy-drift')
            self.host.pause()  # worker quiescence required, never stop/kill worker
            op['status'] = 'running'
            self.save(state)
            try:
                self.restore(state)
            except Exception:
                op['status'] = 'attention'
                self.save(state)
                raise
            self.finish_timer(state)
            return op

    def deploy(self, target, expected):
        target = Path(target)
        with locked(self.root / 'operation.lock'):
            state = self.status()
            self.preflight(state, expected)
            candidate = self.host.validate(target)
            if candidate['compat'] != state['current']['compat']:
                raise Refused('not-code-only')
            self.host.rehearse(target)
            # Recheck after expensive rehearsal, before any production mutation.
            self.preflight(state, expected)
            with locked(self.sync_lock, existing=True):
                schedule = self.host.before_pause()
                op = {'id': uuid.uuid4().hex, 'status': 'running', 'phase': 'pause',
                      'recovery': state['current'], 'candidate': candidate, 'schedule': schedule,
                      'log': str(getattr(self.host, 'log', ''))}
                state['operation'] = op
                self.save(state)
                mutated = False
                try:
                    self.host.pause()
                    self.phase(state, 'cutover')
                    mutated = True  # before stop/pointer, includes after-publication failure
                    self.host.stop_web()
                    if time.time() >= schedule['deadline']:
                        raise Refused('maintenance-window-expired')
                    self.switch(target)
                    self.phase(state, 'start-web')
                    self.host.start_web(target)
                    state['previous'], state['current'] = op['recovery'], candidate
                    op['status'] = 'deployed'
                except Exception as error:
                    op['failure'] = type(error).__name__
                    op['failed_phase'] = op['phase']
                    op['failed_unit'] = getattr(self.host, 'unit', None)
                    if mutated:
                        try:
                            self.restore(state)
                        except Exception:
                            op['status'] = 'attention'
                            self.save(state)
                            return op
                    else:
                        op['status'] = 'refused'
                self.finish_timer(state)
                return op


def stopped(props, populated):
    return (props.get('MainPID') == '0' and props.get('ControlPID') == '0'
            and props.get('ActiveState') in ('inactive', 'failed') and populated is False)


TOOL = Path('/usr/local/lib/stocks-release')
STATE = Path('/var/lib/stocks-release')
STORE = Path('/opt/stocks/simple-releases')
POINTER = Path('/opt/stocks/current')
SYNC_LOCK = Path('/var/lib/stocks-sync/inbox/sync-run.lock')
UNITS = ('stocks.service', 'stocks-proxy.service', 'stocks-sync.service', 'stocks-sync.timer')


def rehearsal_command(release, scratch, actor, nonce, broken=False):
    if actor not in ('stocks', 'stocks-sync') or not re.fullmatch('[0-9a-f]{32}', nonce):
        raise Refused('rehearsal-identity')
    properties = [f'User={actor}', f'Group={actor}', 'SupplementaryGroups=stocks-data',
        'Type=oneshot', 'RemainAfterExit=yes', 'Restart=no', 'TimeoutStartSec=100', 'TimeoutStopSec=10',
        'KillMode=control-group', 'PrivateNetwork=yes', 'PrivateTmp=yes', 'PrivateDevices=yes',
        'ProtectHome=yes', 'ProtectSystem=strict', 'NoNewPrivileges=yes',
        'CapabilityBoundingSet=', 'AmbientCapabilities=', 'RestrictSUIDSGID=yes',
        'ProtectKernelTunables=yes', 'ProtectKernelModules=yes', 'ProtectKernelLogs=yes',
        'ProtectControlGroups=yes', 'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6',
        'InaccessiblePaths=/etc/stocks /var/lib/stocks /var/lib/stocks-data /var/lib/stocks-sync /var/lib/stocks-status /var/lib/stocks-proxy /var/backups/stocks',
        f'ReadWritePaths={scratch}', f'WorkingDirectory={release}',
        'MemoryMax=1G', 'TasksMax=64', 'UMask=0077', 'StandardOutput=journal', 'StandardError=journal']
    command = ['/usr/bin/systemd-run', '--quiet', '--unit=stocks-release-probe-' + nonce]
    for prop in properties:
        command.extend(['--property', prop])
    command += ['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE=1',
                '/usr/bin/python3', '-I', '-B', str(TOOL / 'runtime_probe.py'),
                '--release', str(release), '--scratch', str(scratch), '--actor', actor]
    if broken:
        command.append('--broken')
    return command


MAX_FILES = 20000
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
LINKS = {'.venv/bin/python': '/usr/bin/python3', '.venv/bin/python3': 'python',
         '.venv/bin/python3.14': 'python', '.venv/lib64': 'lib'}


class Refused(RuntimeError):
    """Public-safe fixed diagnostic (never include external stderr/env)."""


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    if not isinstance(name, str) or len(name) > 512:
        raise Refused('path')
    parts = PurePosixPath(name).parts
    if not parts or str(PurePosixPath(name)) != name or any(p in ('..', '/') for p in parts):
        raise Refused('path')
    if not re.fullmatch(r'[A-Za-z0-9_.+/ @=-]+', name):
        raise Refused('path')
    if parts[0] == 'data':
        raise Refused('secret-or-state')
    for p in parts:
        if p in ('.env', '.git', 'node_modules') or p.startswith('.env.') or p.endswith(('.db', '.db-wal', '.db-shm', '.sqlite', '.sqlite3', '.key')):
            raise Refused('secret-or-state')
    if name.endswith('.pem') and name != '.venv/lib/python3.14/site-packages/certifi/cacert.pem':
        raise Refused('secret-or-state')
    return parts


def open_beneath(root, name):
    """No symlink in any component, including root; descriptor-relative reads."""
    parts = safe_name(name)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)


def read_regular(root, name, limit=MAX_FILE):
    fd = open_beneath(root, name)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise Refused('file-type-or-size')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        stable = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if any(getattr(before, k) != getattr(after, k) for k in stable) or len(data) != before.st_size or len(data) > limit:
            raise Refused('source-changed')
        return data
    finally:
        os.close(fd)


def canonical_mode(name):
    return 0o755 if name == 'bin/caddy' or name.startswith('.venv/bin/') else 0o644


def inventory(root, runtime=False):
    root = Path(root)
    rows = []
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        if runtime:
            relative = Path(directory).relative_to(root).as_posix()
            if relative == '.':
                dirs[:] = [d for d in dirs if d in ('.venv','backend','bin','deploy','frontend')]
                files = [f for f in files if f in ('alembic.ini','requirements-production.txt')]
            elif relative == 'frontend':
                dirs[:] = [d for d in dirs if d == 'dist']
                files = []
            elif relative == 'deploy':
                dirs[:] = []
                files = [f for f in files if f == 'Caddyfile']
        for basename in sorted(dirs + files):
            path = Path(directory) / basename
            name = path.relative_to(root).as_posix()
            safe_name(name)
            mode = path.lstat().st_mode
            row = {'path': name}
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                if LINKS.get(name) != target:
                    raise Refused('link')
                row.update(type='link', target=target)
            elif stat.S_ISDIR(mode):
                row.update(type='dir', mode=0o755)
            elif stat.S_ISREG(mode):
                data = read_regular(root, name)
                total += len(data)
                row.update(type='file', mode=canonical_mode(name), size=len(data), sha256=sha(data))
            else:
                raise Refused('file-type')
            rows.append(row)
            if len(rows) > MAX_FILES or total > MAX_TOTAL:
                raise Refused('copy-limit')
    return sorted(rows, key=lambda r: r['path'])


def validate_manifest(data, digest):
    if not re.fullmatch('[0-9a-f]{64}', digest) or sha(data) != digest:
        raise Refused('digest')
    try:
        m = json.loads(data)
        if set(m) != {'format', 'revision', 'runtime', 'files'} or m['format'] != 1 or m['runtime'] != 'CPython-3.14.4' or not re.fullmatch('[0-9a-f]{40}', m['revision']):
            raise ValueError
        rows = m['files']
        if not isinstance(rows, list) or not 0 < len(rows) <= MAX_FILES:
            raise ValueError
        seen = {}
        total = 0
        for row in rows:
            name = row['path']
            safe_name(name)
            if name in seen:
                raise ValueError
            for parent in PurePosixPath(name).parents:
                if str(parent) != '.' and seen.get(str(parent)) != 'dir':
                    raise ValueError
            kind = row['type']
            if kind == 'file':
                if set(row) != {'path','type','mode','size','sha256'} or row['mode'] != canonical_mode(name) or type(row['size']) is not int or not 0 <= row['size'] <= MAX_FILE or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
                    raise ValueError
                total += row['size']
            elif kind == 'dir':
                if set(row) != {'path','type','mode'} or row['mode'] != 0o755:
                    raise ValueError
            elif kind == 'link':
                if set(row) != {'path','type','target'} or LINKS.get(name) != row['target']:
                    raise ValueError
            else:
                raise ValueError
            seen[name] = kind
        if total > MAX_TOTAL:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise Refused('manifest') from None
    return m


def copy_rows(source, destination, rows):
    destination.mkdir(mode=0o755)  # no overwrite; partial failure retained
    destination.chmod(0o755)
    for row in rows:
        name, kind = row['path'], row['type']
        dst = destination / name
        if kind == 'dir':
            dst.mkdir(mode=0o755)
            dst.chmod(0o755)
        elif kind == 'link':
            dst.symlink_to(row['target'])  # fixed allowlist, never chmod target
        else:
            data = read_regular(source, name)
            if len(data) != row['size'] or sha(data) != row['sha256']:
                raise Refused('source-changed')
            with dst.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), row['mode'])
                os.fsync(stream.fileno())


def prepare(source, output, revision):
    source, output = Path(source), Path(output)
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise Refused('revision-format')
    if source.resolve() in output.resolve().parents:
        raise Refused('output-inside-source')
    output.mkdir(mode=0o700)
    rows = inventory(source)
    manifest = encoded({'format': 1, 'revision': revision, 'runtime': 'CPython-3.14.4', 'files': rows})
    validate_manifest(manifest, sha(manifest))
    copy_rows(source, output / 'release', rows)
    (output / 'manifest.json').write_bytes(manifest)
    return sha(manifest)


def stage(bundle, destination, digest):
    bundle, destination = Path(bundle), Path(destination)
    m = validate_manifest(read_regular(bundle, 'manifest.json', MAX_MANIFEST), digest)
    copy_rows(bundle / 'release', destination, m['files'])
    if inventory(destination) != m['files']:
        raise Refused('staged-inventory')
    return m


def admit(bundle, digest):
    manifest = validate_manifest(read_regular(bundle, 'manifest.json', MAX_MANIFEST), digest)
    destination = STORE / digest
    if not destination.exists():
        stage(bundle, destination, digest)
    if inventory(destination) != manifest['files']:
        raise Refused('incomplete-or-changed-stage')
    permissions(destination)
    return destination


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--revision', required=True)
    for name in ('inspect','rehearse','deploy'):
        p = sub.add_parser(name)
        p.add_argument('--bundle', required=True, type=Path)
        p.add_argument('--digest', required=True)
        if name == 'deploy':
            p.add_argument('--expected-current', required=True)
    p = sub.add_parser('adopt')
    p.add_argument('--expected-current', required=True)
    sub.add_parser('status')
    p = sub.add_parser('rollback')
    p.add_argument('--operation', required=True)
    p.add_argument('--expected-current', required=True)
    args = parser.parse_args()
    log = None
    try:
        if args.command == 'prepare':
            if os.geteuid() == 0:
                raise Refused('prepare-must-be-unprivileged')
            result = {'status':'prepared','digest':prepare(args.source, args.output, args.revision)}
        elif args.command == 'inspect':
            m = validate_manifest(read_regular(args.bundle, 'manifest.json', MAX_MANIFEST), args.digest)
            if inventory(args.bundle / 'release') != m['files']:
                raise Refused('bundle-inventory')
            permissions(args.bundle / 'release', owner=os.geteuid())
            result = {'status':'inspected','digest':args.digest,'revision':m['revision'],'entries':len(m['files'])}
        else:
            if os.geteuid() != 0 or Path(__file__).resolve() != TOOL / 'stocks_release.py':
                raise Refused('installed-root-tool-required')
            for path in (TOOL, TOOL / 'stocks_release.py', TOOL / 'runtime_probe.py', STATE, STORE):
                info = path.lstat()
                if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                    raise Refused('installed-owner')
            os.umask(0o077)
            log = STATE / ('operation-' + uuid.uuid4().hex + '.log')
            host = NativeHost(log)
            ctl = Controller(STATE, POINTER, SYNC_LOCK, host)
            if args.command == 'status':
                result = ctl.status()
                result['observed_pointer'] = ctl.current()
                result['units'] = {unit:host.show(unit, ('ActiveState',)) for unit in UNITS}
            elif args.command == 'adopt':
                result = ctl.adopt(args.expected_current)
            elif args.command == 'rollback':
                result = ctl.rollback(args.operation, args.expected_current)
            else:
                target = admit(args.bundle, args.digest)
                if args.command == 'rehearse':
                    with locked(STATE / 'operation.lock'):
                        host.validate(target)
                        host.rehearse(target)
                    result = {'status':'rehearsed','target':str(target)}
                else:
                    result = ctl.deploy(target, args.expected_current)
            result['log'] = str(log)
        print(json.dumps(result, sort_keys=True))
        return {'restored':2, 'attention':3, 'refused':1}.get(result.get('status'), 0)
    except Exception as error:
        message = str(error) if isinstance(error, Refused) else type(error).__name__
        print(json.dumps({'status':'refused','error':message,'log':str(log) if log else None,
                          'state':str(STATE / 'state.json') if log else None}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
