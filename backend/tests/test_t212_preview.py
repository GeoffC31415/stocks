"""Synthetic-only HTTP preview; the POST never reaches systemd, broker or DB."""

import importlib.util
from pathlib import Path

import httpx


def test_synthetic_launcher_disables_dotenv_reads_at_construction(tmp_path, monkeypatch):
    from pydantic_settings import DotEnvSettingsSource

    from app.config import Settings

    synthetic = tmp_path / "synthetic.env"
    synthetic.write_text("PORTFOLIO_TRADING212_API_KEY=SYNTHETIC_ONLY\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("dotenv reads must be disabled before source construction")

    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_file", forbidden)
    assert Settings(_env_file=synthetic).trading212_api_key is None


async def test_preview_simulates_request_and_completion_without_downstream_mutations():
    source = Path(__file__).resolve().parents[2] / "scripts/preview_t212.py"
    assert source.exists(), "Dedicated synthetic Trading 212 preview is required"
    spec = importlib.util.spec_from_file_location("preview_t212", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def forbidden(scope, receive, send):
        raise AssertionError("fixture endpoints must not reach downstream DB/systemd")

    app = module.Trading212Fixture(forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8128"
    ) as client:
        status = await client.get("/api/sync/status")
        assert status.json()["service_trigger_enabled"] is True
        assert (await client.get("/api/trading212/status")).json()["configured"] is False
        response = await client.post(
            "/api/sync/trading212/request", headers={"Origin": "http://127.0.0.1:8128"}
        )
        assert response.status_code == 202
        assert response.json()["state"] == "accepted"
        request_id = response.json()["request_id"]
        assert (await client.get("/api/sync/trading212/request")).json()["state"] == "running"
        terminal = (await client.get("/api/sync/trading212/request")).json()
        assert terminal["request_id"] == request_id
        assert terminal["state"] == "completed"
        assert terminal["last_run"]["steps"][0]["detail"] is None
        assert (await client.post("/api/trading212/sync")).status_code == 405
        assert (
            await client.post(
                "/api/sync/trading212/request?unit=evil",
                headers={"Origin": "http://127.0.0.1:8128"},
            )
        ).status_code == 400
        assert (
            await client.post(
                "/api/sync/trading212/request", headers={"Origin": "https://evil.test"}
            )
        ).status_code == 403
