"""Guarded final passkey cutover. No password fallback or automatic downgrade."""
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path

from broker_isolation import (
    MigrationError,
    authorize_transition,
    exclusive_write,
    parse_env,
    plain,
    strict_json,
    transition_lock,
)
from broker_isolation import (
    System as IsolationSystem,
)


def private(path, root, owner, *, directory=False):
    for p in (path, *path.parents):
        if p == root:
            break
        info = p.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid not in {owner, 0} or info.st_mode & 0o022:
            raise CutoverError('Unsafe path ownership, permissions or symlink.')
        if p == path:
            expected = 0o700 if directory else 0o600
            if stat.S_IMODE(info.st_mode) != expected or info.st_uid != owner:
                raise CutoverError('Expected private owned path.')
            if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise CutoverError('Expected singly linked regular file.')
            if directory and not stat.S_ISDIR(info.st_mode):
                raise CutoverError('Expected private directory.')


def current_release(root, release, owner=0):
    base = root / 'opt/stocks/releases'
    if release.parent != base or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', release.name):
        raise CutoverError('Expected explicit installed release path.')
    for p in (release, *release.parents):
        if p == root:
            break
        info = p.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
            raise CutoverError('Unsafe release path.')
    current = root / 'opt/stocks/current'
    if not current.is_symlink() or current.resolve(strict=True) != release:
        raise CutoverError('Installed release differs from expected release.')


def preflight(root, release, owner, web_owner, now, system=None):
    current_release(root, release, owner)
    config = root / 'etc/stocks/production.env'
    marker = root / 'etc/stocks/isolation.json'
    for path in (config, marker):
        private(path, root, owner)
    bundle = Path(strict_json(marker, root)['bundle'])
    if bundle.parent != root / 'var/backups/stocks' or not re.fullmatch(r'isolation-[A-Za-z0-9_-]+', bundle.name):
        raise CutoverError('Unexpected isolation evidence path.')
    private(bundle, root, owner, directory=True)
    try:
        manifest, _ = authorize_transition(root, bundle, system or IsolationSystem(), activation_only=True, timer_mode='saved')
        if manifest['release'] != str(release):
            raise CutoverError('Isolation release mismatch.')
    except (MigrationError, OSError, ValueError, KeyError):
        raise CutoverError('Isolation candidate or fresh readiness refused.') from None
    original = config.read_bytes()
    values = {key: plain(value) for key, value in parse_env(original.decode()).items()}
    expected = {'AUTH_MODE': 'basic', 'AUTH_DATABASE_PATH': '/var/lib/stocks/auth.sqlite3',
                'PUBLIC_ORIGIN': 'https://solarpi.hopto.org:5000', 'DEPLOYMENT_MODE': 'public'}
    if any(values.get(key) != value for key, value in expected.items()):
        raise CutoverError('Unexpected migration authentication configuration.')
    if not values.get('AUTH_USERNAME') or not values.get('AUTH_PASSWORD_HASH'):
        raise CutoverError('Expected existing Basic migration configuration.')
    from broker_isolation import BROKER_KEYS
    if values.keys() & BROKER_KEYS:
        raise CutoverError('Broker settings must not be in web configuration.')
    auth = root / 'var/lib/stocks/auth.sqlite3'
    private(auth.parent, root, web_owner, directory=True)
    private(auth, root, web_owner)
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(str(auth) + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            private(sidecar, root, web_owner)
    private(root / 'var/backups/stocks', root, owner, directory=True)
    auth_evidence(auth, now=now)
    return config, auth, original


def cutover(root, release, system, *, owner=0, web_owner, now=None):
    with transition_lock(root):
        return _cutover(root, release, system, owner=owner, web_owner=web_owner, now=now)


def _cutover(root, release, system, *, owner=0, web_owner, now=None):
    live_clock = now is None
    now = time.time() if live_clock else now
    config, auth, original = preflight(root, release, owner, web_owner, now, system)
    bundle = Path(tempfile.mkdtemp(prefix='passkey-', dir=root / 'var/backups/stocks'))
    exclusive_write(bundle / 'production.env', original)
    target = bundle / 'auth.sqlite3'
    exclusive_write(target, b'')
    deadline = time.monotonic() + 20
    def progress(*_):
        if time.monotonic() > deadline:
            raise CutoverError('Authentication backup timed out.')
    with closing(sqlite3.connect(auth.as_uri() + '?mode=ro', uri=True, timeout=5)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst, pages=64, progress=progress, sleep=0.05)
        if dst.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise CutoverError('Authentication backup integrity check failed.')
    auth_evidence(target, now=now)
    exclusive_write(bundle / 'manifest.json', json.dumps({'version': 1, 'release': str(release), 'created_at': now,
                    'config': 'production.env', 'auth': 'auth.sqlite3', 'automatic_rollback': False}).encode())
    lines = []
    for line in original.decode().splitlines(keepends=True):
        if line.startswith(('PORTFOLIO_AUTH_USERNAME=', 'PORTFOLIO_AUTH_PASSWORD_HASH=')):
            continue
        lines.append('PORTFOLIO_AUTH_MODE=passkey\n' if line.startswith('PORTFOLIO_AUTH_MODE=') else line)
    final = ''.join(lines).encode()
    # Recheck before commit; failures after replacement never restore Basic.
    preflight(root, release, owner, web_owner, time.time() if live_clock else now, system)
    if config.read_bytes() != original:
        raise CutoverError('Configuration changed during preflight.')
    staged = config.parent / ('cutover-' + bundle.name)
    exclusive_write(staged, final)
    try:
        os.replace(staged, config)
        fd = os.open(config.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        system.stop()
        private(config, root, owner)
        if config.read_bytes() != final:
            raise CutoverError('Configuration readback mismatch.')
        current_release(root, release, owner)
        system.start()
        system.verify()
        exclusive_write(bundle / 'verified', b'1\n')
    except BaseException:  # noqa: BLE001 - fail closed even when interrupted after replacement
        try:
            system.stop()
        except BaseException:  # noqa: BLE001 - interruption must report unconfirmed stop
            raise CutoverError('Cutover incomplete and web stop could not be confirmed; preserve evidence and inspect locally. Never automatically restore Basic.') from None
        raise CutoverError('Cutover incomplete: web service stopped; retain private backups, repair passkey configuration or use local auth recovery. Never automatically restore Basic.') from None
    return bundle


def host_gate(uid, hostname, confirmation):
    if uid != 0 or hostname != 'geoff-Surface-Pro-4' or confirmation != 'PASSKEY-ONLY':
        raise CutoverError('Requires root on geoff-Surface-Pro-4 and --confirm PASSKEY-ONLY.')


def verify_public(request):
    status, body = request('/api/auth/session', 'application/json')
    try:
        state = json.loads(body)
    except (ValueError, UnicodeError):
        raise CutoverError('Public authentication response invalid.') from None
    if status != 200 or not isinstance(state, dict) or state.get('mode') != 'passkey' or state.get('authenticated') is not False:
        raise CutoverError('Public passkey-only mode not verified.')
    if request('/api/health', 'application/json')[0] != 401:
        raise CutoverError('Anonymous protected health must be denied.')
    if request('/', 'text/html')[0] != 200:
        raise CutoverError('Public sign-in page unavailable.')


class System:
    def readiness(self, saved, *, timer_mode='saved'):
        return IsolationSystem().readiness(saved, timer_mode=timer_mode)

    def __init__(self):
        for command in ('/usr/bin/systemctl', '/usr/bin/curl'):
            if not os.access(command, os.X_OK):
                raise CutoverError('Required systemctl/curl command unavailable.')

    def command(self, argv):
        import subprocess
        try:
            result = subprocess.run(argv, capture_output=True, timeout=30, check=True,
                                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            raise CutoverError('Bounded service/public verification command failed.') from None

    def stop(self):
        self.command(['/usr/bin/systemctl', 'stop', 'stocks.service'])

    def start(self):
        self.command(['/usr/bin/systemctl', 'start', 'stocks.service'])

    def request(self, path, accept):
        result = self.command(['/usr/bin/curl', '-q', '--silent', '--show-error', '--noproxy', '*',
            '--proto', '=https', '--resolve', 'solarpi.hopto.org:5000:127.0.0.1',
            '--connect-timeout', '5', '--max-time', '10', '--max-filesize', '1048576',
            '--header', 'Accept: ' + accept, '--write-out', '\n%{http_code}',
            'https://solarpi.hopto.org:5000' + path])
        body, status = result.rsplit(b'\n', 1)
        return int(status), body

    def verify(self):
        for attempt in range(5):
            try:
                verify_public(self.request)
                return
            except CutoverError:
                if attempt == 4:
                    raise
                time.sleep(1)


def main(argv=None):
    import argparse
    import pwd
    import socket
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-current', type=Path, required=True)
    parser.add_argument('--confirm', required=True)
    args = parser.parse_args(argv)
    try:
        host_gate(os.geteuid(), socket.gethostname(), args.confirm)
        system = System()
        uid = pwd.getpwnam('stocks').pw_uid
        if uid == 0:
            raise CutoverError('Web service must not run as root.')
        bundle = cutover(Path('/'), args.expect_current, system, web_owner=uid)
        print('Passkey-only anonymous boundary verified. Owner login still required.')
        print('Private operator evidence:', bundle)
        return 0
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - never leak privileged exception data
        # Never print exception text: OS/JSON/SQLite errors may include secrets.
        print('Cutover refused or incomplete. Inspect private /var/backups/stocks/passkey-* evidence locally; never automatically restore Basic. Check stocks.service is stopped if cutover was started; repair passkey mode or use local auth recovery.', file=sys.stderr)
        return 1


class CutoverError(Exception):
    """Fixed, secret-free operator diagnostic."""


def auth_evidence(path, *, now):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        if db.execute('PRAGMA application_id').fetchone()[0] != 0x53544B41:
            raise CutoverError('Wrong authentication database.')
        if db.execute("SELECT 1 FROM meta WHERE key='recovery_pending' AND value='1'").fetchone():
            raise CutoverError('Recovery pending; finish recovery first.')
        times = [row[0] for row in db.execute('SELECT last_used_at FROM credentials')]
        if not times or any(t is not None and t > now for t in times) or not any(
            t is not None and now - 600 <= t <= now for t in times
        ):
            raise CutoverError('A registered passkey must authenticate within the last ten minutes.')


if __name__ == '__main__':
    raise SystemExit(main())
