"""Public broker execution is denied even for authenticated same-origin requests."""

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.database import get_session
from app.main import create_app
from app.routers.trading212 import get_trading212_client
from app.security import hash_password


@pytest.mark.asyncio
async def test_public_sync_never_reaches_private_credential_gate():
    config = Settings(
        _env_file=None,
        deployment_mode="public",
        public_origin="https://stocks.example.net",
        auth_username="fixture",
        auth_password_hash=hash_password("fixture-password-long"),
    )
    app = create_app(config)

    async def no_database():
        yield None

    calls = []

    def no_broker():
        calls.append(True)
        raise HTTPException(503, "Fixture credential gate reached")

    app.dependency_overrides[get_session] = no_database
    app.dependency_overrides[get_trading212_client] = no_broker
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=config.public_origin,
        auth=("fixture", "fixture-password-long"),
    ) as client:
        response = await client.post(
            "/api/trading212/sync", headers={"Origin": config.public_origin}
        )
        assert calls == []
        assert response.status_code == 403
        for origin in ("https://evil.test", "http://localhost:8000"):
            response = await client.post("/api/trading212/sync", headers={"Origin": origin})
            assert response.status_code == 403
