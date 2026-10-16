"""Checks for full-coverage test scheduling, not application behaviour."""

import importlib.util
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("backend_test_runner", ROOT / "scripts/test_backend.py")


def load_runner():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def test_shards_preserve_every_collected_file_once():
    runner = load_runner()
    files = {
        "backend/tests/test_a.py": 10,
        "backend/tests/test_b.py": 8,
        "backend/tests/test_c.py": 3,
        "backend/tests/test_d.py": 1,
    }
    groups = runner.partition(files, 2, {"backend/tests/test_a.py": 12, "backend/tests/test_b.py": 11})
    flattened = [file for group in groups for file in group]
    assert sorted(flattened) == sorted(files)
    assert len(flattened) == len(set(flattened))
    assert all(groups)
    assert runner.partition(files, 2, {}) == runner.partition(dict(reversed(list(files.items()))), 2, {})


def test_timing_hints_cannot_drop_files_or_inject_paths():
    runner = load_runner()
    files = {"backend/tests/test_a.py": 1, "backend/tests/test_b.py": 2, "backend/tests/test_c.py": 3}
    groups = runner.partition(files, 2, {
        "../../private.py": 1000, "backend/tests/test_a.py": float("nan"),
        "backend/tests/test_b.py": "not-a-number", "backend/tests/test_c.py": 10**1000,
    })
    assert sorted(file for group in groups for file in group) == sorted(files)


def test_collection_parser_refuses_missing_duplicate_and_outside_nodes():
    runner = load_runner()
    output = "backend/tests/test_a.py::test_one\nbackend/tests/test_a.py::test_two[param]\n\n2 tests collected in 0.01s\n"
    assert runner.collected_files(output) == {"backend/tests/test_a.py": 2}
    for bad in ["no tests ran", "../private.py::test_one\n", "backend/tests/test_a.py::test_one\nbackend/tests/test_a.py::test_one\n"]:
        with pytest.raises(ValueError):
            runner.collected_files(bad)


def test_runner_preserves_callers_permission_semantics(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner.sys, "argv", ["test_backend.py", "--output", str(tmp_path / "results")])

    def collect(*args, **kwargs):
        assert kwargs.get("umask") == 0o022
        raise RuntimeError("stop after checking collection bootstrap")

    monkeypatch.setattr(runner.subprocess, "Popen", collect)
    original = os.umask(0o022)
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with pytest.raises(RuntimeError, match="stop after checking"):
            runner.main()
        restored_umask = os.umask(0o022)
        assert restored_umask == 0o022
        assert {sig: signal.getsignal(sig) for sig in handlers} == handlers
    finally:
        os.umask(original)


@pytest.fixture
def synthetic_runner(tmp_path):
    """Real tiny processes, never a recursive invocation of pytest."""
    launcher = tmp_path / "launcher.py"
    launcher.write_text('''
import os, pathlib, sys, time
root = pathlib.Path(__file__).parent
if "--collect-only" in sys.argv and not (root / "collect-block").exists():
    print("backend/tests/test_a.py::test_one\\nbackend/tests/test_b.py::test_one\\n2 tests collected")
else:
    (root / (str(os.getpid()) + ".pid")).write_text(str(os.getpid()))
    while True:
        time.sleep(.01)
''')
    wrapper = tmp_path / "runner.py"
    wrapper.write_text(f'''
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("runner", {str(SPEC.origin)!r})
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.LAUNCHER = pathlib.Path({str(launcher)!r})
sys.exit(runner.main())
''')
    return wrapper


def wait_until(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    pytest.fail("synthetic subprocess did not reach the expected state")


@pytest.mark.parametrize("failure", ["cancel_during_start", "second_shard_fails"])
def test_startup_cleanup_restores_process_state(synthetic_runner, monkeypatch, failure):
    runner = load_runner()
    root = synthetic_runner.parent
    monkeypatch.setattr(runner, "LAUNCHER", root / "launcher.py")
    monkeypatch.setattr(sys, "argv", ["test_backend.py", "--output", str(root / "results")])
    popen = subprocess.Popen
    children = []
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    original_umask = os.umask(0o022)

    def start(command, **options):
        if len(children) == 2 and failure == "second_shard_fails":
            raise OSError("synthetic startup failure")
        child = popen(command, **options)
        children.append(child)
        if len(children) == 2 and failure == "cancel_during_start":
            os.kill(os.getpid(), signal.SIGTERM)
        return child

    monkeypatch.setattr(subprocess, "Popen", start)
    try:
        expected = SystemExit if failure == "cancel_during_start" else OSError
        with pytest.raises(expected):
            runner.main()
        assert all(child.returncode is not None for child in children)
        assert all(not Path(f"/proc/{child.pid}").exists() for child in children)
        assert {sig: signal.getsignal(sig) for sig in handlers} == handlers
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(original_umask)
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=8)


@pytest.mark.parametrize("cancel_signal", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize("phase", ["shards", "collection"])
def test_cancellation_reaps_owned_processes(synthetic_runner, cancel_signal, phase):
    root = synthetic_runner.parent
    if phase == "collection":
        (root / "collect-block").touch()
    process = subprocess.Popen(
        [sys.executable, str(synthetic_runner), "--output", str(root / "results")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    owned = []
    try:
        wait_until(lambda: len(list(root.glob("*.pid"))) == (2 if phase == "shards" else 1))
        owned = [int(path.read_text()) for path in root.glob("*.pid")]
        process.send_signal(cancel_signal)
        process.wait(timeout=8)
        assert all(not Path(f"/proc/{pid}").exists() for pid in owned), "runner left owned children alive/unreaped"
        assert process.returncode == 128 + cancel_signal
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=8)
        for path in root.glob("*.pid"):
            with suppress(ProcessLookupError):
                os.kill(int(path.read_text()), signal.SIGKILL)
