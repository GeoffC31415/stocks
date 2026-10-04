"""Synthetic dedicated policy gate tests: no root/services/private files."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

MODULE = Path(__file__).resolve().parents[2] / 'deploy/stocks_t212_verify.py'


@pytest.fixture
def gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('t212_gate', MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = {'files': dict.fromkeys(module.FILES, hashlib.sha256(b'fixed').hexdigest()), 'worker_sha256': hashlib.sha256(b'fixed').hexdigest()}
    monkeypatch.setattr(module, 'trusted_file', lambda path: json.dumps(policy).encode() if Path(path)==module.POLICY else b'fixed')
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(module.Path, 'stat', lambda *args, **kwargs: Mock(st_mode=0o600))
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: Mock(stdout=b''))
    return module, policy


def test_exact_policy_passes(gate, capsys):
    gate[0].verify()
    assert 'verified' in capsys.readouterr().out


def test_modified_policy_refuses(gate):
    module, policy = gate
    policy['files'][module.FILES[0]] = '0'*64
    with pytest.raises(ValueError, match='policy-drift'):
        module.verify()


def test_unreviewed_dropin_refuses(gate, monkeypatch):
    module, _ = gate
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: Mock(stdout=b'/etc/systemd/system/stocks-t212-sync.service.d/evil.conf'))
    with pytest.raises(ValueError, match='drop-ins'):
        module.verify()


def test_modified_worker_refuses(gate):
    module, policy = gate
    policy['worker_sha256'] = '0'*64
    with pytest.raises(ValueError, match='worker-drift'):
        module.verify()
