"""Operational review regressions. No live systemctl mutations."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sr_operational', ROOT / 'deploy/simple_release/stocks_release.py')
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


@pytest.mark.parametrize('delay,initial', [(40, 1000), (0, 999)])
def test_timer_resumption_rechecks_after_observations_and_reserves_start(tmp_path, monkeypatch, delay, initial):
    host = sr.NativeHost(tmp_path / 'private.log')
    clock = [float(initial)]
    starts = []
    monkeypatch.setattr(sr.time, 'time', lambda: clock[0])
    monkeypatch.setattr(sr.time, 'monotonic', lambda: clock[0] - 500)
    saved = {'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'started_wall': 701., 'started_mono': 201., 'deadline': 1001., 'enabled': 'enabled'}
    def quiescent(unit, **kwargs):
        clock[0] += delay
    def show(unit, keys, **kwargs):
        clock[0] += delay
        return {'UnitFileState': 'enabled', 'ActiveState': 'active'}
    monkeypatch.setattr(host, 'quiescent', quiescent)
    monkeypatch.setattr(host, 'show', show)
    monkeypatch.setattr(host, 'run', lambda argv, **kwargs: starts.append(argv) or '')
    assert host.restore_timer(saved) is False
    assert starts == []  # Cannot issue start late, even if each query was within its bound.


@pytest.mark.parametrize('bad_readback', [False, True])
def test_timer_restore_bounded_command_and_full_readback(tmp_path, monkeypatch, bad_readback):
    host = sr.NativeHost(tmp_path / 'private.log')
    calls = []
    monkeypatch.setattr(sr.time, 'time', lambda: 900.)
    monkeypatch.setattr(sr.time, 'monotonic', lambda: 400.)
    saved = {'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'started_wall': 701., 'started_mono': 201., 'deadline': 1001., 'enabled': 'enabled'}
    props = {'ActiveState': 'active', 'UnitFileState': 'enabled', 'Persistent': 'yes',
             'RandomizedDelayUSec': '2min', 'NextElapseUSecRealtime': '@1182',
             'TimersCalendar': '{ OnCalendar=*-*-* 18:30:00 Europe/London ; next_elapse=@1062 }'}
    if bad_readback:
        props['Persistent'] = 'unknown'
    monkeypatch.setattr(host, 'quiescent', lambda *a, **k: None)
    monkeypatch.setattr(host, 'show', lambda *a, **k: props)
    monkeypatch.setattr(host, 'run', lambda argv, **kw: calls.append((argv, kw)) or '')
    assert host.restore_timer(saved) is not bad_readback
    assert calls[0] == (['/usr/bin/systemctl', 'start', 'stocks-sync.timer'], {'timeout': 5})
    assert len(calls) == (2 if bad_readback else 1)
    if bad_readback:
        assert calls[-1][0] == ['/usr/bin/systemctl', 'stop', 'stocks-sync.timer']


def test_web_start_waits_for_readiness_without_restarting(tmp_path, monkeypatch):
    host = sr.NativeHost(tmp_path / 'private.log')
    clock = [0.]
    calls = []
    monkeypatch.setattr(sr.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(sr.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    monkeypatch.setattr(host, 'run', lambda argv, **kw: calls.append(argv) or '')
    def verify(target, **kwargs):
        if clock[0] < 4:
            raise sr.Refused('https-auth-boundary')
    monkeypatch.setattr(host, 'verify_web', verify)
    host.start_web(tmp_path)
    assert 4 <= clock[0] <= 60
    assert calls == [['/usr/bin/systemctl', 'start', unit] for unit in sr.UNITS[:2]]


@pytest.mark.parametrize('reason,bounded', [('https-auth-boundary', True), ('web-release-mismatch', False)])
def test_readiness_eventually_refuses_without_restarting_units(tmp_path, monkeypatch, reason, bounded):
    host = sr.NativeHost(tmp_path / 'private.log')
    clock = [0.]
    starts = []
    monkeypatch.setattr(sr.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(sr.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    monkeypatch.setattr(host, 'run', lambda argv, **kw: starts.append(argv) or '')
    def fail(*args, **kwargs):
        raise sr.Refused(reason)
    monkeypatch.setattr(host, 'verify_web', fail)
    with pytest.raises(sr.Refused, match='web-readiness-timeout' if bounded else reason):
        host.start_web(tmp_path)
    assert clock[0] == (60 if bounded else 0)
    assert len(starts) == 2


def test_native_rehearsal_masks_host_run_and_pid_namespace():
    command = sr.rehearsal_command(Path('/opt/release'), Path('/var/lib/scratch'), 'stocks', 'a' * 32)
    assert 'TemporaryFileSystem=/run:ro' in command
    assert 'PrivatePIDs=yes' in command
    assert 'PrivateIPC=yes' in command
    assert '--host-pid-namespace' in command
    assert '--ipc-canary' in command


@pytest.mark.parametrize('private_run,private_pid,expected', [
    (True, True, 'isolated'), (False, True, 'host-ipc-reachable'),
    (True, False, 'host-pid-namespace')])
def test_real_disposable_socket_and_pid_negative_controls(private_run, private_pid, expected):
    import json
    import os
    import socket
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix='sr-ipc-', dir=os.environ['TMPDIR']) as directory:
        run = Path(directory)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(run / 'canary.sock'))
            listener.listen(1)
            args = ['/usr/bin/bwrap', '--unshare-user', '--unshare-net', '--die-with-parent',
                    '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
                    '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
                    '--dev', '/dev', '--ro-bind', str(run), '/run',
                    '--ro-bind', str(ROOT / 'deploy/simple_release/runtime_probe.py'), '/probe.py']
            args += ['--unshare-pid', '--proc', '/proc'] if private_pid else ['--ro-bind', '/proc', '/proc']
            if private_run:
                args += ['--tmpfs', '/run']
            code = ('import importlib.util,json,sys; from pathlib import Path; '
                    's=importlib.util.spec_from_file_location("probe","/probe.py"); '
                    'p=importlib.util.module_from_spec(s); s.loader.exec_module(p);\n'
                    'try:\n p.check_host_isolation(sys.argv[1],Path("/run/canary.sock")); print(json.dumps("isolated"))\n'
                    'except RuntimeError as e: print(json.dumps(str(e)))\n')
            args += ['--', '/usr/bin/python3', '-I', '-B', '-c', code, os.readlink('/proc/self/ns/pid')]
            result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == expected
