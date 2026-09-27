"""Auth HTTP tests never execute lifespan, migrations or portfolio connections."""

import httpx
import pytest
from test_passkeys import ORIGIN, Authenticator

from app.config import Settings


@pytest.fixture
def config(tmp_path, monkeypatch):
    import app.database as database
    import app.main as main
    from app.security import hash_password

    def forbidden(*args, **kwargs):
        raise AssertionError("Portfolio DB/startup forbidden")

    monkeypatch.setattr(database.engine.sync_engine, "connect", forbidden)
    monkeypatch.setattr(main, "init_db", forbidden)
    return Settings(
        _env_file=None,
        deployment_mode="public",
        auth_mode="basic",
        public_origin=ORIGIN,
        auth_username="owner",
        auth_password_hash=hash_password("synthetic"),
        auth_database_path=tmp_path / "auth.db",
        frontend_dist=tmp_path / "frontend",
    )


@pytest.mark.asyncio
async def test_basic_enrollment_then_passkey_only_cutover(config):
    from app.main import create_app

    basic = ("owner", "synthetic")
    app = create_app(config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        status = await client.get("/api/auth/session", auth=basic)
        assert status.status_code == 200
        assert status.json() == {
            "mode": "basic",
            "authenticated": True,
            "passkey_authenticated": False,
            "can_register": True,
            "expires_at": None,
        }
        assert (
            await client.post("/api/auth/register/options", json={"label": "Key"})
        ).status_code == 403
        response = await client.post(
            "/api/auth/register/options", json={"label": "Dashlane"}, auth=basic
        )
        assert response.status_code == 200
        issued = response.json()
        assert issued["options"]["rp"]["id"] == "solarpi.hopto.org"
        assert issued["options"]["attestation"] == "none"
        assert issued["options"]["authenticatorSelection"]["residentKey"] == "required"
        key = Authenticator()
        response = await client.post(
            "/api/auth/register/verify",
            json={
                "ceremony_id": issued["ceremony_id"],
                "credential": key.register(issued["options"]),
            },
        )
        assert response.status_code == 200
        assert response.json()["passkey_authenticated"]
        cookie = response.headers["set-cookie"]
        for flag in ["__Host-stocks_session=", "Secure", "HttpOnly", "SameSite=strict", "Path=/"]:
            assert flag in cookie
        assert "Domain=" not in cookie
        assert "token" not in response.text
        assert (
            await client.get("/api/health")
        ).status_code == 401  # Session doesn't replace Basic yet.
        assert (await client.get("/api/health", auth=basic)).status_code == 200
        credentials = (await client.get("/api/auth/credentials")).json()["credentials"]
        assert credentials[0]["label"] == "Dashlane"
        config = config.model_copy(
            update={"auth_mode": "passkey", "auth_username": None, "auth_password_hash": None}
        )
        new_app = create_app(config)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=new_app),
            base_url=ORIGIN,
            cookies=client.cookies,
            headers={"Origin": ORIGIN},
        ) as session_client:
            assert (await session_client.get("/api/health")).status_code == 200
            assert (await session_client.post("/api/auth/logout", json={})).status_code == 200
            assert (await session_client.get("/api/health", auth=basic)).status_code == 401
            issued = (await session_client.post("/api/auth/login/options", json={})).json()
            response = await session_client.post(
                "/api/auth/login/verify",
                json={
                    "ceremony_id": issued["ceremony_id"],
                    "credential": key.assertion(issued["options"]),
                },
            )
            assert response.status_code == 200
            assert response.json()["mode"] == "passkey"
            assert (await session_client.get("/api/health")).status_code == 200


@pytest.mark.asyncio
async def test_empty_passkey_store_public_shell_but_never_api_or_docs(config):
    from app.main import create_app

    config = config.model_copy(
        update={"auth_mode": "passkey", "auth_username": None, "auth_password_hash": None}
    )
    config.frontend_dist.mkdir()
    (config.frontend_dist / "index.html").write_text("<html>Public login shell</html>")
    (config.frontend_dist / "assets").mkdir()
    (config.frontend_dist / "assets/app.js").write_text("console.log('shell')")
    (config.frontend_dist / "secret.txt").write_text("not-public")
    app = create_app(config)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        for path in ["/", "/portfolio", "/settings/security", "/assets/app.js"]:
            response = await client.get(path, headers={"Accept": "text/html"})
            assert response.status_code == 200, path
        for path in [
            "/api/health",
            "/api/auth/credentials",
            "/docs",
            "/openapi.json",
            "/secret.txt",
            "/api/auth/unknown",
        ]:
            assert (await client.get(path, auth=("owner", "synthetic"))).status_code == 401, path
        status = (await client.get("/api/auth/session")).json()
        assert status == {
            "mode": "passkey",
            "authenticated": False,
            "passkey_authenticated": False,
            "can_register": False,
            "expires_at": None,
        }
        assert (
            await client.post(
                "/api/auth/register/options",
                json={"label": "No fallback"},
                headers={"Origin": ORIGIN},
                auth=("owner", "synthetic"),
            )
        ).status_code == 403
        for endpoint in [
            "login/options",
            "login/verify",
            "register/options",
            "register/verify",
            "recovery/options",
        ]:
            response = await client.post("/api/auth/" + endpoint, json={})
            assert response.status_code == 403
            assert response.headers["cache-control"] == "no-store"
        response = await client.post(
            "/api/auth/recovery/options",
            json={"token": "sentinel-secret"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 422
        assert "sentinel-secret" not in response.text
        response = await client.post(
            "/api/auth/login/options", content=b"x" * 16385, headers={"Origin": ORIGIN}
        )
        assert response.status_code == 413


def test_passkey_config_requires_explicit_store_but_not_basic_hash(config):
    from pydantic import ValidationError

    from app.security import validate_public_settings

    validate_public_settings(
        config.model_copy(update={"auth_mode": "passkey", "auth_password_hash": None})
    )
    with pytest.raises(RuntimeError):
        validate_public_settings(
            config.model_copy(update={"auth_mode": "passkey", "auth_database_path": None})
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_session_idle_seconds=86401)


@pytest.mark.asyncio
async def test_local_status_is_authenticated_without_store():
    from app.main import create_app

    app = create_app(Settings(_env_file=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        assert (await client.get("/api/auth/session")).json() == {
            "mode": "local",
            "authenticated": True,
            "passkey_authenticated": False,
            "can_register": False,
            "expires_at": None,
        }
