"""Completion evidence tests: synthetic filesystem and service adapters only."""
from pathlib import Path

import pytest
from test_isolation_migration import FakeSystem, deployment_fixture, helper


@pytest.mark.parametrize("phase", ["activation", "rollback"])
def test_real_pending_unlink_interrupt_failed_invalidation_refuses(tmp_path, monkeypatch, phase):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    if phase == "rollback":
        m.rollback_layout(root, bundle, system)
    # Preserve the real historical failure as a legacy-refusal regression.
    (bundle / "transition.json").unlink()
    completion = bundle / (phase + "-complete")
    pending = completion.with_name(completion.name + "-pending")
    unlink = Path.unlink
    def fault(path, *a, **kw):
        if path == pending:
            unlink(path, *a, **kw)
            raise KeyboardInterrupt("after real unlink")
        if path == completion:
            raise OSError("invalidation failed")
        return unlink(path, *a, **kw)
    monkeypatch.setattr(Path, "unlink", fault)
    with pytest.raises(OSError):
        try:
            m.exclusive_write(pending, b"1\n")
            m.exclusive_write(completion, b"1\n")
            pending.unlink()
        except BaseException:
            try:
                completion.unlink()
            finally:
                system.stop()
    assert completion.exists() and not pending.exists()
    assert not system.web_active
    fresh_module = helper()
    fresh = fresh_module.System()
    calls = []
    fresh.command = lambda *a, **kw: calls.append(a) or ("enabled" if a[1] == "is-enabled" else "active")
    with pytest.raises(fresh_module.MigrationError, match="evidence unavailable"):
        fresh.resume_timer(bundle, root=root)
    assert not calls


def test_resume_uses_candidate_and_rechecks_before_mutation(tmp_path):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    fake = FakeSystem()
    m.activate_layout(root, bundle, release, previous, fake)
    system = m.System()
    probes, calls = [], []
    def readiness(saved, **kw):
        probes.append(True)
        return fake.readiness(saved, **kw)
    def command(*a, **kw):
        assert len(probes) == 2
        calls.append(a[1])
        return "enabled" if a[1] == "is-enabled" else "active"
    system.readiness, system.command = readiness, command
    system.resume_timer(bundle, root=root)
    assert calls == ["enable", "start", "is-enabled", "is-active"]


def test_candidate_binds_manifest_marker_and_fresh_identity(tmp_path):
    import json
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    candidate = json.loads((bundle / "transition.json").read_text())
    manifest = json.loads((bundle / "manifest.json").read_text())
    marker = json.loads((root / "etc/stocks/isolation.json").read_text())
    assert candidate["state"] == "verified_candidate"
    assert manifest["version"] == marker["version"] == candidate["version"] == 2
    assert candidate["transition_id"] == manifest["transition_id"] == marker["transition_id"]
    assert m.authorize_transition(root, bundle, system)[0] == manifest
    system.web_active = False
    with pytest.raises(m.MigrationError):
        m.authorize_transition(root, bundle, system)


def test_inactive_restored_web_is_not_resume_ready(tmp_path):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    system.snapshot = lambda: {"timer_active": False, "timer_enabled": "disabled", "web_active": False, "worker_active": False}
    m.activate_layout(root, bundle, release, previous, system)
    m.rollback_layout(root, bundle, system)
    assert not system.web_active
    with pytest.raises(m.MigrationError, match='no live identity'):
        m.authorize_transition(root, bundle, system)


@pytest.mark.parametrize("phase", ["activation", "rollback"])
@pytest.mark.parametrize("point", ["flush", "fsync", "close", "replace-before", "replace-after", "directory-fsync", "directory-close", "readback"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_publication_faults_preserve_evidence_and_fresh_reader_refuses(tmp_path, monkeypatch, phase, point, error_type):
    import json
    import os
    import stat
    from contextlib import contextmanager
    from unittest.mock import Mock
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    if phase == "rollback":
        m.activate_layout(root, bundle, release, previous, system)
    publish = m.publish_transition
    observed = []
    def publishing(root, bundle, manifest, phase, state, identity=None):
        if state != "verified_candidate":
            return publish(root, bundle, manifest, phase, state, identity)
        fdopen, fsync, replace, close, read = m.os.fdopen, m.os.fsync, m.os.replace, m.os.close, m.strict_json
        def fail():
            observed.append(True)
            raise error_type("SENTINEL")
        @contextmanager
        def stream(fd, *a, **kw):
            with fdopen(fd, *a, **kw) as out:
                proxy = Mock(wraps=out)
                if point == "flush":
                    def flush():
                        out.flush()
                        fail()
                    proxy.flush.side_effect = flush
                yield proxy
            if point == "close":
                fail()
        def sync(fd):
            fsync(fd)
            directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            if point == ("directory-fsync" if directory else "fsync"):
                fail()
        def replacing(src, dst):
            if point == "replace-before":
                fail()
            replace(src, dst)
            if point == "replace-after":
                fail()
        def closing(fd):
            directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            close(fd)
            if directory and point == "directory-close":
                fail()
        def reading(path, root):
            result = read(path, root)
            if path.name == "transition.json":
                fail()
            return result
        with monkeypatch.context() as patch:
            patch.setattr(m.os, "fdopen", stream)
            patch.setattr(m.os, "fsync", sync)
            patch.setattr(m.os, "replace", replacing)
            patch.setattr(m.os, "close", closing)
            if point == "readback":
                patch.setattr(m, "strict_json", reading)
            return publish(root, bundle, manifest, phase, state, identity)
    monkeypatch.setattr(m, "publish_transition", publishing)
    with pytest.raises(error_type):
        if phase == "activation":
            m.activate_layout(root, bundle, release, previous, system)
        else:
            m.rollback_layout(root, bundle, system)
    assert observed == [True]
    assert not system.web_active
    state = json.loads((bundle / "transition.json").read_text())["state"]
    assert state == ("verified_candidate" if point in {"replace-after", "directory-fsync", "directory-close", "readback"} else "preparing")
    fresh_module = helper()
    fresh = fresh_module.System()
    fresh.readiness = system.readiness
    calls = []
    fresh.command = lambda *a, **kw: calls.append(a)
    with pytest.raises(fresh_module.MigrationError):
        fresh.resume_timer(bundle, root=root)
    assert calls == []
    if phase == "activation":
        # Successful rollback supersedes failure without deleting partial temps.
        temps = set(bundle.glob('.transition-*'))
        monkeypatch.setattr(m, "publish_transition", publish)
        m.rollback_layout(root, bundle, system)
        assert temps <= set(bundle.glob('.transition-*'))
        assert m.authorize_transition(root, bundle, system)[1]["phase"] == "rollback"


@pytest.mark.parametrize("phase", ["activation", "rollback"])
@pytest.mark.parametrize("enabled", ["enabled", "disabled"])
@pytest.mark.parametrize("active", [True, False])
def test_saved_timer_restoration_exact(tmp_path, phase, enabled, active):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    fake = FakeSystem()
    fake.snapshot = lambda: {"timer_enabled": enabled, "timer_active": active, "web_active": True, "worker_active": False}
    m.activate_layout(root, bundle, release, previous, fake)
    if phase == "rollback":
        m.rollback_layout(root, bundle, fake)
    system = m.System()
    system.readiness = fake.readiness
    state = {"enabled": "disabled", "active": False}
    calls = []
    def command(*a, **kw):
        action = a[1]
        calls.append(action)
        if action in ("enable", "disable"):
            state["enabled"] = "enabled" if action == "enable" else "disabled"
        elif action in ("start", "stop"):
            state["active"] = action == "start"
        elif action == "is-enabled":
            return state["enabled"]
        elif action == "is-active":
            return "active" if state["active"] else "inactive"
    system.command = command
    system.resume_timer(bundle, root=root)
    assert state == {"enabled": enabled, "active": active}
    assert calls[-2:] == ["is-enabled", "is-active"]


@pytest.mark.parametrize("hazard", ["missing", "legacy", "duplicate", "version", "type", "extra", "phase", "preparing", "digest", "id", "bundle", "mode", "owner", "symlink", "hardlink", "truncated"])
def test_candidate_strict_refusal_before_probes(tmp_path, monkeypatch, hazard):
    import json
    import os
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    m.activate_layout(root, bundle, release, previous, FakeSystem())
    path = bundle / "transition.json"
    obj = json.loads(path.read_text())
    if hazard == "missing":
        path.unlink()
    elif hazard == "legacy":
        (bundle / "manifest.json").write_text('{"version":1}')
    elif hazard == "duplicate":
        path.write_text('{"version":2,' + path.read_text()[1:])
    elif hazard == "truncated":
        path.write_text('{')
    elif hazard == "mode":
        path.chmod(0o644)
    elif hazard == "owner":
        original = Path.lstat
        def other_owner(p, *a, **kw):
            info = original(p, *a, **kw)
            if p == path:
                fields = list(info)
                fields[4] += 1
                return os.stat_result(fields)
            return info
        monkeypatch.setattr(Path, "lstat", other_owner)
    elif hazard in ("symlink", "hardlink"):
        alias = bundle / 'alias'
        if hazard == 'hardlink':
            os.link(path, alias)
        else:
            path.rename(alias)
            path.symlink_to(alias)
    else:
        key, value = {"version": ("version", 3), "type": ("version", True), "extra": ("unknown", 0), "phase": ("phase", "other"), "preparing": ("state", "preparing"), "digest": ("manifest_sha256", "0" * 64), "id": ("transition_id", "0" * 32), "bundle": ("bundle", "/wrong")}[hazard]
        obj[key] = value
        path.write_text(json.dumps(obj))
    system = m.System()
    system.command = lambda *a, **kw: pytest.fail("host commands forbidden")
    with pytest.raises(m.MigrationError):
        system.resume_timer(bundle, root=root)


@pytest.mark.parametrize("change", ["stopped", "restarted", "rebooted", "effective", "probe", "current", "config", "during-final-probe"])
def test_fresh_and_last_moment_drift_refuses_timer_mutations(tmp_path, change):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    fake = FakeSystem()
    m.activate_layout(root, bundle, release, previous, fake)
    system = m.System()
    probes = []
    def readiness(saved, **kw):
        probes.append(True)
        value = fake.readiness(saved)
        if change == 'probe':
            raise m.MigrationError('Probe failed.')
        if len(probes) == 2:
            if change == 'during-final-probe':
                (root / 'etc/stocks/production.env').write_text('drift')
            if change == 'stopped':
                return None
            if change in ('restarted', 'rebooted', 'effective'):
                value[{"restarted": "invocation_id", "rebooted": "boot_id", "effective": "effective_sha256"}[change]] = 'changed'
        if len(probes) == 1:
            if change == 'current':
                m.switch_release(root, previous)
            if change == 'config':
                (root / 'etc/stocks/production.env').write_text('drift')
        return value
    system.readiness = readiness
    calls = []
    system.command = lambda *a, **kw: calls.append(a)
    with pytest.raises(m.MigrationError):
        system.resume_timer(bundle, root=root)
    assert calls == []


@pytest.mark.parametrize("hazard", ["held", "symlink", "mode", "hardlink"])
def test_lock_refuses_before_transition_mutations(tmp_path, hazard):
    import os
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    lock = root / 'etc/stocks/.completion.lock'
    system = FakeSystem()
    if hazard == 'held':
        with m.transition_lock(root), pytest.raises(m.MigrationError):
            m.activate_layout(root, bundle, release, previous, system)
    else:
        lock.write_text('')
        lock.chmod(0o600)
        if hazard == 'mode':
            lock.chmod(0o644)
        elif hazard == 'hardlink':
            os.link(lock, lock.with_name('alias'))
        else:
            lock.unlink()
            lock.symlink_to(root / 'etc/stocks/production.env')
        with pytest.raises((m.MigrationError, OSError)):
            m.activate_layout(root, bundle, release, previous, system)
    assert system.events == []
    assert not (bundle / 'manifest.json').exists()


@pytest.mark.parametrize('when', ['before', 'after', 'readback'])
@pytest.mark.parametrize('cleanup', ['ok', 'failed'])
def test_timer_mutation_failure_attempts_safe_cleanup(tmp_path, when, cleanup):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    fake = FakeSystem()
    m.activate_layout(root, bundle, release, previous, fake)
    system = m.System()
    system.readiness = fake.readiness
    state = {'enabled': 'disabled', 'active': 'inactive'}
    calls = []
    def command(*a, **kw):
        action = a[1]
        calls.append(a)
        if action == 'enable':
            if when == 'before':
                raise KeyboardInterrupt()
            state['enabled'] = 'enabled'
            if when == 'after':
                raise KeyboardInterrupt()
        elif action == 'start':
            state['active'] = 'active'
        elif action == 'disable':
            if cleanup == 'failed':
                raise OSError('SENTINEL')
            state.update(enabled='disabled', active='inactive')
        elif action == 'is-enabled':
            return state['enabled']
        elif action == 'is-active':
            return 'activating' if when == 'readback' and state['enabled'] == 'enabled' else state['active']
    system.command = command
    error = m.MigrationError if cleanup == 'failed' or when == 'readback' else KeyboardInterrupt
    with pytest.raises(error) as caught:
        system.resume_timer(bundle, root=root)
    assert any(c[1:3] == ('disable', '--now') for c in calls)
    if cleanup == 'failed':
        assert 'stop could not be confirmed' in str(caught.value)
    else:
        assert state == {'enabled': 'disabled', 'active': 'inactive'}
