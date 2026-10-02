"""Standalone release contracts: all paths are disposable; no live mutations."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / 'deploy/simple_release/stocks_release.py'
spec = importlib.util.spec_from_file_location('simple_release', MODULE)
sr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sr
if MODULE.exists():
    spec.loader.exec_module(sr)


def source(tmp_path):
    root = tmp_path / 'source'
    (root / 'backend/app').mkdir(parents=True)
    (root / 'backend/app/main.py').write_text('unchanged bytes')
    for path in [root, *root.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return root


@pytest.mark.parametrize('name,kind', [('.env','file'), ('portfolio.db','file'), ('escape','link'), ('pipe','fifo')])
def test_prepare_refuses_secret_state_or_unsafe_type(tmp_path, name, kind):
    src = source(tmp_path)
    p = src / name
    if kind == 'link':
        p.symlink_to('/etc/passwd')
    elif kind == 'fifo':
        os.mkfifo(p)
    else:
        p.write_text('must not copy')
    with pytest.raises(sr.Refused):
        sr.prepare(src, tmp_path / 'bundle', 'a' * 40)


def test_stage_digest_boundary_and_runtime_links(tmp_path):
    src = source(tmp_path)
    (src / '.venv/bin').mkdir(parents=True)
    (src / '.venv/bin/python').symlink_to('/usr/bin/python3')
    (src / '.venv/bin/python3').symlink_to('python')
    out = tmp_path / 'bundle'
    digest = sr.prepare(src, out, 'a' * 40)
    with pytest.raises(sr.Refused, match='digest'):
        sr.stage(out, tmp_path / 'bad', '0' * 64)
    sr.stage(out, tmp_path / 'good', digest)
    assert (tmp_path / 'good/.venv/bin/python').is_symlink()
    assert (tmp_path / 'good/backend/app/main.py').stat().st_mode & 0o777 == 0o644
    with pytest.raises(FileExistsError):
        sr.stage(out, tmp_path / 'good', digest)


def test_read_only_access_time_is_not_source_mutation(tmp_path):
    src = source(tmp_path)
    file = src / 'backend/app/main.py'
    os.utime(file, (1, 1))
    assert sr.read_regular(src, 'backend/app/main.py') == b'unchanged bytes'


@pytest.mark.parametrize('change', ['traversal', 'duplicate', 'link-parent', 'oversize'])
def test_malformed_manifest(tmp_path, change):
    out = tmp_path / 'bundle'
    digest = sr.prepare(source(tmp_path), out, 'a' * 40)
    m = sr.validate_manifest((out / 'manifest.json').read_bytes(), digest)
    if change == 'traversal':
        m['files'][-1]['path'] = '../escape'
    elif change == 'duplicate':
        m['files'].append(m['files'][-1])
    elif change == 'link-parent':
        m['files'][0] = {'path':'backend','type':'link','target':'/etc'}
    else:
        m['files'][-1]['size'] = sr.MAX_FILE + 1
    data = sr.encoded(m)
    with pytest.raises(sr.Refused):
        sr.validate_manifest(data, sr.sha(data))


def test_staging_source_replacement_and_bound(tmp_path, monkeypatch):
    src = source(tmp_path)
    out = tmp_path / 'bundle'
    digest = sr.prepare(src, out, 'a' * 40)
    (out / 'release/backend/app/main.py').write_text('tampered')
    with pytest.raises(sr.Refused, match='source-changed'):
        sr.stage(out, tmp_path / 'staged', digest)
    monkeypatch.setattr(sr, 'MAX_TOTAL', 1)
    with pytest.raises(sr.Refused, match='copy-limit'):
        sr.prepare(src, tmp_path / 'oversize', 'a' * 40)


class FakeHost:
    def __init__(self):
        self.events = []
        self.fail_candidate = False
        self.uncertain_timer = False
        self.active_sync = False
    def verify_web(self, target):
        if getattr(self, 'wrong_web', False):
            raise sr.Refused('web-release-mismatch')
    def fingerprint(self):
        return 'stable'
    def validate(self, path):
        if not (path / 'ok').exists():
            raise sr.Refused('invalid-release')
        return {'path': str(path), 'compat': 'schema', 'inventory': 'trusted'}
    def rehearse(self, path):
        self.events.append('rehearse')
    def before_pause(self):
        if self.active_sync:
            raise sr.Refused('sync-active')
        return {'deadline': sr.time.time() + 300}
    def pause(self):
        self.events.append('pause')
    def stop_web(self):
        self.events.append('stop')
    def start_web(self, target):
        self.events.append('start-' + target.name)
        if self.fail_candidate and target.name == 'new':
            raise sr.Refused('candidate-start')
    def restore_timer(self, saved):
        self.events.append('timer')
        return not self.uncertain_timer


def controller(tmp_path):
    for n in ['old', 'new']:
        (tmp_path / n).mkdir()
        (tmp_path / n / 'ok').write_text(n)
    (tmp_path / 'current').symlink_to(tmp_path / 'old')
    host = FakeHost()
    (tmp_path / 'sync-run.lock').touch(mode=0o600)
    ctl = sr.Controller(tmp_path / 'state', tmp_path / 'current', tmp_path / 'sync-run.lock', host)
    ctl.adopt(str(tmp_path / 'old'))
    return ctl, host


def test_actual_pointer_publication_failure_restores_old(tmp_path, monkeypatch):
    ctl, host = controller(tmp_path)
    original = ctl.switch
    def after_write(target):
        original(target)
        if target.name == 'new':
            assert Path(os.readlink(ctl.pointer)) == tmp_path / 'new'
            raise sr.Refused('after-publication')
    monkeypatch.setattr(ctl, 'switch', after_write)
    result = ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert result['status'] == 'restored'
    assert ctl.pointer.resolve() == tmp_path / 'old'
    assert host.events[-2:] == ['start-old', 'timer']
    assert ctl.status()['operation']['status'] == 'restored'


@pytest.mark.parametrize('reason', ['current', 'worker', 'lock', 'permissions', 'web'])
def test_preflight_refuses_before_cutover(tmp_path, reason):
    ctl, host = controller(tmp_path)
    expected = str(tmp_path / 'old')
    if reason == 'current':
        expected += '-wrong'
    elif reason == 'worker':
        host.active_sync = True
    elif reason == 'web':
        host.wrong_web = True
    elif reason == 'permissions':
        (tmp_path / 'new/ok').unlink()
    if reason == 'lock':
        with sr.locked(ctl.sync_lock), pytest.raises(sr.Refused, match='busy'):
            ctl.deploy(tmp_path / 'new', expected)
    else:
        with pytest.raises(sr.Refused):
            ctl.deploy(tmp_path / 'new', expected)
    assert ctl.pointer.resolve() == tmp_path / 'old'
    assert 'pause' not in host.events


def test_failed_start_and_uncertain_timer_restore_web(tmp_path):
    ctl, host = controller(tmp_path)
    host.fail_candidate = True
    host.uncertain_timer = True
    result = ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert result['status'] == 'attention'
    assert not result['timer_restored']
    assert ctl.pointer.resolve() == tmp_path / 'old'
    assert 'start-old' in host.events


def test_interrupted_deploy_recovery_ignores_failed_candidate(tmp_path, monkeypatch):
    ctl, host = controller(tmp_path)
    original = host.start_web
    def crash(target):
        if target.name == 'new':
            raise KeyboardInterrupt()
        return original(target)
    monkeypatch.setattr(host, 'start_web', crash)
    with pytest.raises(KeyboardInterrupt):
        ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert ctl.status()['operation']['status'] == 'running'
    assert ctl.pointer.resolve() == tmp_path / 'new'
    (tmp_path / 'new/ok').unlink()
    with pytest.raises(sr.Refused):
        ctl.deploy(tmp_path / 'new', str(tmp_path / 'new'))
    op_id = ctl.status()['operation']['id']
    result = ctl.rollback(op_id, str(tmp_path / 'new'))
    assert result['status'] == 'restored'
    assert ctl.pointer.resolve() == tmp_path / 'old'


@pytest.mark.parametrize('main,control,populated,state,ok', [
    (0,0,False,'failed',True), (1,0,False,'failed',False),
    (0,2,False,'failed',False), (0,0,True,'failed',False),
    (0,0,False,'activating',False), (0,0,False,'inactive',True)])
def test_stopped_proof_requires_zero_pids_and_empty_cgroup(main, control, populated, state, ok):
    props = {'MainPID':str(main),'ControlPID':str(control),'ActiveState':state}
    assert sr.stopped(props, populated) is ok


def test_fixed_sandbox_uses_real_identity_no_production_env():
    argv = sr.rehearsal_command(Path('/opt/stocks/simple-releases/abc'), Path('/var/lib/stocks-release/rehearsal/abc'), 'stocks-sync', 'a'*32)
    text = ' '.join(argv)
    for value in ['User=stocks-sync','Group=stocks-sync','SupplementaryGroups=stocks-data',
                  'PrivateNetwork=yes','ProtectHome=yes','NoNewPrivileges=yes','CapabilityBoundingSet=',
                  'InaccessiblePaths=/etc/stocks /var/lib/stocks /var/lib/stocks-data /var/lib/stocks-sync /var/lib/stocks-status',
                  'runtime_probe.py']:
        assert value in text
    assert 'EnvironmentFile=' not in text
    assert 'app.sync_cli' not in text
    assert '--collect' not in text  # preserve actual failed state for diagnosis


def test_native_failed_unit_resets_only_after_stopped_proof(tmp_path, monkeypatch):
    host = sr.NativeHost(tmp_path / 'operation.log')
    events = []
    monkeypatch.setattr(host, 'run', lambda argv, **kw: events.append(argv) or '')
    props = {'ActiveState':'failed', 'MainPID':'0', 'ControlPID':'0', 'ControlGroup':''}
    monkeypatch.setattr(host, 'show', lambda unit, keys: props)
    monkeypatch.setattr(host, 'populated', lambda unit, p: False)
    host.stop_unit('stocks.service')
    assert events == [['/usr/bin/systemctl','stop','stocks.service'], ['/usr/bin/systemctl','reset-failed','stocks.service']]
    events.clear()
    props['MainPID'] = '44'
    with pytest.raises(sr.Refused, match='not-stopped'):
        host.stop_unit('stocks.service')
    assert all('reset-failed' not in cmd for cmd in events)


def test_schedule_uses_earliest_unrandomized_deadline():
    props = {'ActiveState':'active','UnitFileState':'enabled', 'Persistent':'yes',
             'NextElapseUSecRealtime':'@1120', 'RandomizedDelayUSec':'2min',
             'TimersCalendar':'{ OnCalendar=*-*-* 18:30:00 Europe/London ; next_elapse=@1000 }'}
    assert sr.schedule_window(props, now=100)['deadline'] == 400
    with pytest.raises(sr.Refused, match='schedule-window'):
        sr.schedule_window(props, now=700)


def test_permission_audit_checks_actual_modes(tmp_path):
    src = source(tmp_path)
    sr.permissions(src, owner=os.getuid())
    (src / 'backend/app/main.py').chmod(0o600)
    with pytest.raises(sr.Refused, match='runtime-permission'):
        sr.permissions(src, owner=os.getuid())


def test_code_only_compatibility_covers_startup_and_migrations():
    rows = [{'path':p,'type':'file','sha256':'a'*64} for p in sr.COMPAT_FILES]
    rows.append({'path':'backend/alembic/versions/001.py','type':'file','sha256':'b'*64})
    original = sr.compatibility(rows)
    rows.append({'path':'frontend/dist/assets/x.js','type':'file','sha256':'c'*64})
    assert sr.compatibility(rows) == original
    rows[-2]['sha256'] = 'd'*64
    assert sr.compatibility(rows) != original


def test_stable_exec_parser_ignores_process_fields_not_arguments():
    one = '{ path=/x ; argv[]=/x --only barclays ; ignore_errors=no ; start_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }'
    two = one.replace('pid=0','pid=999').replace('start_time=[n/a]','start_time=Fri')
    assert sr.stable_exec(one) == sr.stable_exec(two)
    assert sr.stable_exec(one) != sr.stable_exec(one.replace('barclays','hl'))


def test_public_unit_policy_readonly_host_format(tmp_path):
    host = sr.NativeHost(tmp_path / 'public.log')
    policy = host.public_policy()
    assert policy['stocks.service']['User'] == 'stocks'
    assert policy['stocks-sync.service']['SupplementaryGroups'] == 'stocks-data'
    assert policy['stocks-sync.service']['ExecStart'][1].endswith('app.sync_cli --only barclays')


def test_actual_old_and_new_startup_schema_and_lock_inputs_match():
    old = Path('/opt/stocks/releases/stocks-passkeys-31590ff')
    new = Path('/home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3/release')
    a, b = sr.inventory(old, runtime=True), sr.inventory(new, runtime=True)
    assert sr.compatibility(a) == sr.compatibility(b)
    assert sr.lock_contract(old) == sr.lock_contract(new)
    sr.permissions(old, rows=a)


def test_native_validates_existing_immutable_runtime_without_private_config(tmp_path):
    old = Path('/opt/stocks/releases/stocks-passkeys-31590ff')
    value = sr.NativeHost(tmp_path / 'log').validate(old)
    assert value['path'] == str(old)
    assert len(value['compat']) == 64 and len(value['inventory']) == 64


def test_native_starts_both_coupled_units_and_verifies_target(tmp_path, monkeypatch):
    host = sr.NativeHost(tmp_path / 'log')
    events = []
    monkeypatch.setattr(host, 'run', lambda argv, **kw: events.append(argv) or '')
    monkeypatch.setattr(host, 'verify_web', lambda target, **kw: events.append(['verify',str(target)]))
    monkeypatch.setattr(sr.time, 'sleep', lambda seconds: None)
    host.start_web(tmp_path)
    assert events[:2] == [['/usr/bin/systemctl','start','stocks.service'], ['/usr/bin/systemctl','start','stocks-proxy.service']]
    assert events[-1] == ['verify', str(tmp_path)]


def test_rehearsal_has_both_actors_and_failed_start_restore(tmp_path, monkeypatch):
    host = sr.NativeHost(tmp_path / 'log')
    monkeypatch.setattr(sr, 'STATE', tmp_path)
    (tmp_path / 'rehearsal').mkdir()
    src = tmp_path / 'runtime'
    watchfiles = src / '.venv/lib/python3.14/site-packages/watchfiles/__init__.py'
    watchfiles.parent.mkdir(parents=True)
    watchfiles.write_text('# fixture')
    calls = []
    def probe(release, actor, broken=False):
        calls.append((actor,broken))
        if broken:
            assert release.is_symlink()
            assert release.resolve() != src
            assert (release / '.venv/lib/python3.14/site-packages/watchfiles/__init__.py').stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(host, 'probe_once', probe)
    result = host.rehearse(src)
    assert Path(result['fixture_pointer']).resolve() == src
    assert calls == [('stocks',False),('stocks-sync',False),('stocks',True),('stocks',False)]


def test_fingerprint_tracks_private_configuration_without_logging_it(tmp_path, monkeypatch):
    host = sr.NativeHost(tmp_path / 'log')
    monkeypatch.setattr(host, 'public_policy', lambda: {'stable':'policy'})
    monkeypatch.setattr(sr, 'private_config', lambda: 'old-config-digest')
    before = host.fingerprint()
    monkeypatch.setattr(sr, 'private_config', lambda: 'new-config-digest')
    assert host.fingerprint() != before
    assert not (tmp_path / 'log').exists()


def test_cli_prepare_inspect_and_no_unprivileged_deploy(tmp_path):
    import subprocess
    src = source(tmp_path)
    cmd = [sys.executable, '-B', str(MODULE)]
    result = subprocess.run(cmd + ['prepare','--source',str(src),'--output',str(tmp_path / 'out'), '--revision','a'*40], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)['digest']
    result = subprocess.run(cmd + ['inspect','--bundle',str(tmp_path / 'out'),'--digest',digest], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    result = subprocess.run(cmd + ['deploy','--bundle',str(tmp_path / 'out'),'--digest',digest, '--expected-current','/opt/stocks/releases/old'], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert json.loads(result.stdout)['error'] == 'installed-root-tool-required'


def test_missing_existing_sync_lock_refuses_without_creating_root_inode(tmp_path):
    ctl, host = controller(tmp_path)
    ctl.sync_lock.unlink()
    with pytest.raises(FileNotFoundError):
        ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert not ctl.sync_lock.exists()
    assert 'pause' not in host.events


def test_installer_refuses_nonroot_without_mutations():
    import subprocess
    result = subprocess.run(['/bin/bash', str(MODULE.with_name('install.sh')), str(MODULE.parent), '0'*64, '1'*64], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert 'administrator-only' in result.stderr


def test_adopt_requires_running_process_release_agrees(tmp_path):
    ctl, host = controller(tmp_path)
    ctl.record.unlink()
    host.wrong_web = True
    with pytest.raises(sr.Refused, match='web-release-mismatch'):
        ctl.adopt(str(tmp_path / 'old'))
    assert not ctl.record.exists()


def test_source_change_during_descriptor_read_refuses(tmp_path, monkeypatch):
    src = source(tmp_path)
    real = sr.os.fstat
    calls = []
    def changed(fd):
        calls.append(fd)
        if len(calls) == 2:
            (src / 'backend/app/main.py').write_bytes(b'changed bytes!!')
        return real(fd)
    monkeypatch.setattr(sr.os, 'fstat', changed)
    with pytest.raises(sr.Refused, match='source-changed'):
        sr.read_regular(src, 'backend/app/main.py')


def test_operation_result_names_phase_unit_and_private_log(tmp_path):
    ctl, host = controller(tmp_path)
    host.fail_candidate = True
    host.log = tmp_path / 'private.log'
    host.unit = 'stocks.service'
    result = ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert result['failed_phase'] == 'start-web'
    assert result['failure_reason'] == 'candidate-start'
    assert result['failed_unit'] == 'stocks.service'
    assert result['log'] == str(host.log)


def test_command_timeout_preserves_stderr_privately(tmp_path, monkeypatch):
    import subprocess
    host = sr.NativeHost(tmp_path / 'private.log')
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b'partial output', stderr=b'partial stderr')
    monkeypatch.setattr(sr.subprocess, 'run', timeout)
    with pytest.raises(sr.Refused, match='host-command-failed'):
        host.run(['/usr/bin/systemctl','start','stocks.service'])
    assert b'partial stderr' in host.log.read_bytes()
    assert host.log.stat().st_mode & 0o777 == 0o600


def test_window_expiry_after_stop_restores_without_starting_candidate(tmp_path, monkeypatch):
    ctl, host = controller(tmp_path)
    clock = [1000]
    monkeypatch.setattr(sr.time, 'time', lambda: clock[0])
    original = host.stop_web
    def slow_stop():
        original()
        clock[0] = 1400
    monkeypatch.setattr(host, 'stop_web', slow_stop)
    result = ctl.deploy(tmp_path / 'new', str(tmp_path / 'old'))
    assert result['status'] == 'restored'
    assert 'start-new' not in host.events
    assert ctl.pointer.resolve() == tmp_path / 'old'


def test_required_caddy_is_executable_by_service_nonowner(tmp_path):
    src = source(tmp_path)
    (src / 'bin').mkdir(mode=0o755)
    (src / 'bin').chmod(0o755)
    (src / 'bin/caddy').write_bytes(b'fixture')
    (src / 'bin/caddy').chmod(0o744)
    with pytest.raises(sr.Refused, match='runtime-permission'):
        sr.permissions(src, owner=os.getuid())


def test_prepare_rejects_owner_only_runtime(tmp_path):
    src = source(tmp_path)
    code = src / 'backend/app/main.py'
    code.chmod(0o600)
    out = tmp_path / 'bundle'
    digest = sr.prepare(src, out, 'a' * 40)
    assert len(digest) == 64
    assert json.loads((out / 'manifest.json').read_text())['runtime'] == 'CPython-3.14.4'
    copied = out / 'release/backend/app/main.py'
    assert copied.read_bytes() == code.read_bytes()
    assert copied.stat().st_mode & 0o777 == 0o644
    assert code.stat().st_mode & 0o777 == 0o600
    assert out.stat().st_mode & 0o777 == 0o700
