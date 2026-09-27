"""Disposable synthetic files only; never connect to an installed service."""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pytest
from test_isolation_migration import FakeSystem, deployment_fixture, helper

DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'
sys.path.insert(0, str(DEPLOY))


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def module(self):
        spec = importlib.util.spec_from_file_location('cutover', DEPLOY / 'passkey_cutover.py')
        self.assertIsNotNone(spec)
        self.assertTrue(Path(spec.origin).exists(), 'cutover helper is missing')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def database(self, used):
        path = self.root / 'auth.sqlite3'
        with sqlite3.connect(path) as db:
            db.executescript('PRAGMA application_id=0x53544B41; CREATE TABLE credentials (last_used_at REAL); CREATE TABLE meta(key TEXT, value TEXT);')
            db.execute('INSERT INTO credentials VALUES (?)', (used,))
        path.chmod(0o600)
        return path

    def test_registration_without_real_authentication_refused(self):
        m = self.module()
        with self.assertRaises(m.CutoverError):
            m.auth_evidence(self.database(None), now=1000)

    def legacy_fixture(self):
        import json
        m = self.module()
        for name in ('etc/stocks', 'var/lib/stocks', 'var/backups/stocks/isolation-test', 'opt/stocks/releases/test'):
            (self.root / name).mkdir(parents=True, mode=0o700)
        for path in self.root.rglob('*'):
            if path.is_dir():
                path.chmod(0o700)
        release = self.root / 'opt/stocks/releases/test'
        (self.root / 'opt/stocks/current').symlink_to(release)
        bundle = self.root / 'var/backups/stocks/isolation-test'
        for name, text in [('manifest.json', json.dumps({'release': str(release)})), ('activation-complete', '1'), ('state-complete', '1')]:
            (bundle / name).write_text(text)
            (bundle / name).chmod(0o600)
        marker = self.root / 'etc/stocks/isolation.json'
        marker.write_text(json.dumps({'bundle': str(bundle)}))
        marker.chmod(0o600)
        config = self.root / 'etc/stocks/production.env'
        config.write_text('PORTFOLIO_AUTH_MODE=basic\nPORTFOLIO_DEPLOYMENT_MODE=public\nPORTFOLIO_PUBLIC_ORIGIN=https://solarpi.hopto.org:5000\nPORTFOLIO_AUTH_DATABASE_PATH=/var/lib/stocks/auth.sqlite3\nPORTFOLIO_AUTH_USERNAME=synthetic\nPORTFOLIO_AUTH_PASSWORD_HASH=synthetic\n')
        config.chmod(0o600)
        self.database(999).rename(self.root / 'var/lib/stocks/auth.sqlite3')
        return m, release, config

    def fixture(self):
        m = self.module()
        self.root, bundle, release, previous = deployment_fixture(self.root)
        helper().activate_layout(self.root, bundle, release, previous, FakeSystem())
        (self.root / 'var/lib/stocks').chmod(0o700)
        (self.root / 'var/backups/stocks').chmod(0o700)
        self.database(999).rename(self.root / 'var/lib/stocks/auth.sqlite3')
        m.IsolationSystem = FakeSystem  # All service/network adapters remain synthetic.
        return m, release, self.root / 'etc/stocks/production.env'

    def test_cutover_preserves_evidence_removes_fallback_and_checks_public(self):
        import json
        m, release, config = self.fixture()
        before = config.read_bytes()
        actions = []
        class System(FakeSystem):
            def stop(self): actions.append('stop')
            def start(self): actions.append('start')
            def verify(self): actions.append('verify')
        saved = m.cutover(self.root, release, System(), owner=os.getuid(), web_owner=os.getuid(), now=1000)
        self.assertEqual(actions, ['stop', 'start', 'verify'])
        self.assertEqual((saved / 'production.env').read_bytes(), before)
        self.assertEqual(config.read_text(), before.decode().replace('AUTH_MODE=basic', 'AUTH_MODE=passkey').replace('PORTFOLIO_AUTH_USERNAME=owner\n', '').replace('PORTFOLIO_AUTH_PASSWORD_HASH=SENTINEL_AUTH\n', ''))
        self.assertEqual(json.loads((saved / 'manifest.json').read_text())['release'], str(release))
        for name in ('production.env', 'auth.sqlite3', 'manifest.json'):
            self.assertEqual((saved / name).stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(saved / 'auth.sqlite3') as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone(), ('ok',))

    def test_public_probe_requires_exact_mode_and_statuses(self):
        m = self.module()
        calls = []
        def request(path, accept):
            calls.append((path, accept))
            return {'/api/auth/session': (200, b'{"mode":"passkey","authenticated":false}'), '/api/health': (401, b''), '/': (200, b'html')}[path]
        m.verify_public(request)
        self.assertEqual(calls[-1], ('/', 'text/html'))
        for data in (b'{"mode":"basic","authenticated":false}', b'{"mode":"passkey","authenticated":true}'):
            with self.assertRaises(m.CutoverError):
                m.verify_public(lambda path, accept, data=data: (200, data))
        with self.assertRaises(m.CutoverError):
            m.verify_public(lambda path, accept: (200, b'{"mode":"passkey","authenticated":false}'))

    def test_legacy_completion_refused_before_backups(self):
        m, release, config = self.legacy_fixture()
        original = config.read_bytes()
        class System(FakeSystem):
            def stop(self): pass
            def start(self): pass
            def verify(self): pass
        with self.assertRaises(m.CutoverError):
            m.cutover(self.root, release, System(), owner=os.getuid(), web_owner=os.getuid(), now=1000)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(list((self.root / 'var/backups/stocks').glob('passkey-*')), [])

    def test_cutover_cleanup_failure_is_honest(self):
        m, release, config = self.fixture()
        class System(FakeSystem):
            def stop(self): raise OSError('SENTINEL')
        with self.assertRaisesRegex(m.CutoverError, 'stop could not be confirmed'):
            m.cutover(self.root, release, System(), owner=os.getuid(), web_owner=os.getuid(), now=1000)
        self.assertIn('AUTH_MODE=passkey', config.read_text())

    def test_host_gate(self):
        m = self.module()
        for uid, host, confirm in [(1, 'geoff-Surface-Pro-4', 'PASSKEY-ONLY'), (0, 'other', 'PASSKEY-ONLY'), (0, 'geoff-Surface-Pro-4', 'yes')]:
            with self.assertRaises(m.CutoverError):
                m.host_gate(uid, host, confirm)
        m.host_gate(0, 'geoff-Surface-Pro-4', 'PASSKEY-ONLY')

    def test_bad_evidence_rejected(self):
        m = self.module()
        path = self.database(999)
        for used in (None, 399, 1001):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE credentials SET last_used_at=?', (used,))
            with self.assertRaises(m.CutoverError):
                m.auth_evidence(path, now=1000)
        with sqlite3.connect(path) as db:
            db.execute('UPDATE credentials SET last_used_at=999')
            db.execute("INSERT INTO meta VALUES ('recovery_pending','1')")
        with self.assertRaises(m.CutoverError):
            m.auth_evidence(path, now=1000)

    def test_post_write_failure_never_restores_basic(self):
        m, release, config = self.fixture()
        actions = []
        class System(FakeSystem):
            def stop(self): actions.append('stop')
            def start(self): actions.append('start')
            def verify(self): raise RuntimeError('SYNTHETIC_SECRET')
        with self.assertRaises(m.CutoverError) as error:
            m.cutover(self.root, release, System(), owner=os.getuid(), web_owner=os.getuid(), now=1000)
        self.assertNotIn('SYNTHETIC_SECRET', str(error.exception))
        self.assertIn('AUTH_MODE=passkey', config.read_text())
        self.assertNotIn('AUTH_PASSWORD_HASH', config.read_text())
        self.assertEqual(actions[-1], 'stop')

    def test_unsafe_config_and_duplicate_refused_without_service_calls(self):
        from broker_isolation import MigrationError

        m, release, config = self.fixture()
        original = config.read_text()
        for text in (original + 'PORTFOLIO_AUTH_MODE=basic\n', original + 'UNKNOWN=secret\n', original.replace('AUTH_MODE=basic', 'AUTH_MODE=passkey')):
            config.write_text(text)
            with self.assertRaises((m.CutoverError, MigrationError)):
                m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)
        config.write_text(original)
        config.chmod(0o644)
        with self.assertRaises(m.CutoverError):
            m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)
        config.chmod(0o600)
        alias = config.with_name('alias')
        os.link(config, alias)
        with self.assertRaises(m.CutoverError):
            m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)
        alias.unlink()
        config.rename(alias)
        config.symlink_to(alias)
        with self.assertRaises(m.CutoverError):
            m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)

    def test_cutover_system_starts_backend_and_proxy_together(self):
        m = self.module()
        system = m.System()
        calls = []
        system.command = lambda argv: calls.append(argv)

        system.start()

        self.assertEqual(calls, [[
            '/usr/bin/systemctl', 'start', 'stocks.service', 'stocks-proxy.service'
        ]])

    def test_cli_wired_and_transport_uses_verified_tls_without_credentials(self):
        import subprocess
        from unittest.mock import patch
        m = self.module()
        result = subprocess.run([sys.executable, str(DEPLOY / 'passkey_cutover.py'), '--help'], capture_output=True, text=True)
        self.assertIn('--expect-current', result.stdout)
        with patch('subprocess.run') as run:
            run.return_value.stdout = b'{}\n200'
            system = m.System()
            self.assertEqual(system.request('/api/auth/session', 'application/json'), (200, b'{}'))
            argv = run.call_args.args[0]
            self.assertIn('--resolve', argv)
            self.assertNotIn('--insecure', argv)
            self.assertNotIn('-k', argv)
            self.assertEqual(argv[1], '-q')
            self.assertNotIn('shell', run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs['timeout'], 30)

    def test_auth_marker_and_backup_path_refusals(self):
        import json
        m, release, config = self.fixture()
        auth = self.root / 'var/lib/stocks/auth.sqlite3'
        marker = self.root / 'etc/stocks/isolation.json'
        bundle = self.root / 'var/backups/stocks/isolation-fixture'
        def denied():
            with self.assertRaises((m.CutoverError, OSError)):
                m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)
        for path in (auth, marker, bundle / 'manifest.json', self.root / 'var/backups/stocks'):
            mode = path.stat().st_mode & 0o777
            path.chmod(0o777)
            denied()
            path.chmod(mode)
        candidate = (bundle / 'transition.json').read_bytes()
        (bundle / 'transition.json').unlink()
        denied()
        (bundle / 'transition.json').write_bytes(candidate)
        (bundle / 'transition.json').chmod(0o600)
        manifest = (bundle / 'manifest.json').read_bytes()
        (bundle / 'manifest.json').write_text(json.dumps({'release': '/wrong'}))
        denied()
        (bundle / 'manifest.json').write_bytes(manifest)
        with sqlite3.connect(auth) as db:
            db.execute('PRAGMA application_id=0')
        denied()
        with sqlite3.connect(auth) as db:
            db.execute('PRAGMA application_id=0x53544B41')
            db.execute('DELETE FROM credentials')
        denied()

    def test_authentication_that_expires_during_backup_refuses_commit(self):
        from unittest.mock import patch
        m, release, config = self.fixture()
        original = config.read_bytes()
        with patch.object(m.time, 'time', side_effect=[1000, 1601]), self.assertRaises(m.CutoverError):
            m.cutover(self.root, release, FakeSystem(), owner=os.getuid(), web_owner=os.getuid())
        self.assertEqual(config.read_bytes(), original)


    def test_release_requires_expected_immutable_owner(self):
        from unittest.mock import patch

        m, release, _ = self.fixture()
        original_lstat = Path.lstat

        def unrelated_owner(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == release:
                values = list(info)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return info

        with patch.object(Path, 'lstat', unrelated_owner), self.assertRaises(m.CutoverError):
            m.preflight(self.root, release, os.getuid(), os.getuid(), 1000)


@pytest.mark.parametrize('hazard', ['stopped', 'invocation', 'rollback', 'preparing', 'second-drift', 'lock'])
def test_cutover_shared_candidate_readiness_refuses(hazard):
    import json
    case = CutoverTests()
    case.setUp()
    try:
        m, release, config = case.fixture()
        before = config.read_bytes()
        bundle = case.root / 'var/backups/stocks/isolation-fixture'
        system = FakeSystem()
        probes = []
        original_readiness = system.readiness
        def readiness(saved, *, timer_mode):
            assert timer_mode == 'saved'  # Restored schedule is allowed, not forced disabled.
            probes.append(True)
            value = original_readiness(saved)
            if hazard == 'stopped':
                return None
            if hazard == 'invocation':
                value['invocation_id'] = '3' * 32
            if hazard == 'second-drift' and len(probes) == 2:
                (case.root / 'etc/stocks/brokers.env').write_text('drift')
            return value
        system.readiness = readiness
        if hazard in ('rollback', 'preparing'):
            record = json.loads((bundle / 'transition.json').read_text())
            record['phase' if hazard == 'rollback' else 'state'] = hazard
            (bundle / 'transition.json').write_text(json.dumps(record))
        if hazard == 'lock':
            with m.transition_lock(case.root), pytest.raises(m.MigrationError):
                m.cutover(case.root, release, system, owner=os.getuid(), web_owner=os.getuid(), now=1000)
        else:
            with pytest.raises(m.CutoverError):
                m.cutover(case.root, release, system, owner=os.getuid(), web_owner=os.getuid(), now=1000)
        assert config.read_bytes() == before
        assert system.events == []
        if hazard != 'second-drift':
            assert list((case.root / 'var/backups/stocks').glob('passkey-*')) == []
    finally:
        case.doCleanups()


if __name__ == '__main__':
    unittest.main()
