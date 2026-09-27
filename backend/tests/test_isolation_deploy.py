"""Static unit contracts; no installed units or privileged operations."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_unit_identities_env_and_paths_are_separate():
    web = (ROOT / "deploy/stocks.service").read_text()
    worker = (ROOT / "deploy/stocks-sync.service").read_text()
    assert "User=stocks\n" in web
    assert "User=stocks-sync\n" in worker
    assert "EnvironmentFile=/etc/stocks/production.env" in web
    assert "brokers.env" not in web
    assert "production.env" not in worker
    assert "EnvironmentFile=/etc/stocks/brokers.env" in worker
    for unit in (web, worker):
        assert "SupplementaryGroups=stocks-data" in unit
        assert "ReadWritePaths=/var/lib/stocks-data" in unit
        assert "UMask=0007" in unit  # DB and newly created WAL/SHM stay group writable
    assert "StateDirectory=stocks\n" in web
    assert "StateDirectory=stocks-sync\n" in worker
    assert "ReadOnlyPaths=/var/lib/stocks-status" in web
    assert "InaccessiblePaths=-/var/lib/stocks-sync" in web
    assert "InaccessiblePaths=-/var/lib/stocks\n" in worker
    assert "PORTFOLIO_SYNC_CONTROL_DIR=/var/lib/stocks/control" in web
    assert "ReadWritePaths=/var/lib/stocks-status" in worker


def test_legacy_activation_fails_closed_before_any_sudo():
    for script, mode in [("install-surface.sh", "--install"), ("upgrade-surface.sh", "--upgrade"), ("install-surface.sh", "--activate"), ("upgrade-surface.sh", "--activate")]:
        result = subprocess.run(["bash", str(ROOT / "deploy" / script), mode], text=True, capture_output=True)
        assert result.returncode != 0
        assert "broker-isolation" in result.stderr
