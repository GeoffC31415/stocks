"""Run pytest without dotenv or production database configuration."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
for key in tuple(os.environ):
    if key.startswith("PORTFOLIO_"):
        del os.environ[key]
os.environ["PORTFOLIO_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["PYTHONPATH"] = str(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
# Disable file discovery before importing any application or pytest plugins.
from pydantic_settings import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
DotEnvSettingsSource.__call__ = lambda self: {}
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
