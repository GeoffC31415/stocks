"""Safety contracts for the loopback-only, synthetic passkey rehearsal."""
import importlib.util
from pathlib import Path

import pytest


def harness():
    path = Path(__file__).resolve().parents[2] / 'scripts/verify_passkeys.py'
    spec = importlib.util.spec_from_file_location('passkey_rehearsal', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rehearsal_scrubs_inherited_portfolio_secrets(tmp_path):
    module = harness()
    env = module.rehearsal_environment(
        {'PATH': '/usr/bin', 'PORTFOLIO_HL_PASSWORD': 'synthetic-secret',
         'PORTFOLIO_DATABASE_URL': 'sqlite:////must-not-open.db',
         'PORTFOLIO_OTHER_SECRET': 'synthetic-secret'},
        tmp_path, tmp_path / 'dist', 'https://localhost:49123', 'synthetic-hash', 'basic',
    )
    assert 'PORTFOLIO_HL_PASSWORD' not in env
    assert 'PORTFOLIO_OTHER_SECRET' not in env
    assert env['PORTFOLIO_DATABASE_URL'] == f"sqlite+aiosqlite:///{tmp_path / 'portfolio-synthetic.db'}"
    assert env['PORTFOLIO_AUTH_DATABASE_PATH'] == str(tmp_path / 'auth.sqlite3')
    assert env['PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED'] == 'false'


def test_rehearsal_rejects_nonloopback_origin(tmp_path):
    with pytest.raises(ValueError):
        harness().rehearsal_environment({}, tmp_path, tmp_path, 'https://solarpi.hopto.org:5000', 'hash', 'basic')


def test_proxy_is_private_and_never_uses_public_acme():
    config = harness().proxy_config(49123, 49124)
    assert 'bind 127.0.0.1' in config
    assert 'admin off' in config
    assert 'auto_https disable_redirects' in config
    assert 'skip_install_trust' in config
    assert 'tls internal' in config
    assert 'acme' not in config
