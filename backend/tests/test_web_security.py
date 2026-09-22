"""Web boundary tests: synthetic ASGI requests, never the production database."""

import importlib.util
from pathlib import Path

import httpx
import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def forbid_production_database(monkeypatch):
    import app.database as database
    import app.main as main

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("Production database connections are forbidden")

    async def forbidden_migration():
        raise AssertionError("Unmocked application lifespan is forbidden")

    monkeypatch.setattr(database.engine.sync_engine, "connect", forbidden_connection)
    monkeypatch.setattr(database, "_run_migrations", forbidden_connection)
    monkeypatch.setattr(main, "init_db", forbidden_migration)


@pytest.fixture
def public_config(tmp_path):
    from app.security import hash_password

    return Settings(
        _env_file=None,
        deployment_mode="public",
        public_origin="https://example.test",
        auth_username="owner",
        auth_password_hash=hash_password("test-password"),
        frontend_dist=tmp_path / "not-built",
    )


@pytest.fixture
def public_app(public_config):
    from fastapi import Request

    from app.main import create_app

    application = create_app(public_config)
    application.state.writes = []
    from app.database import get_session

    async def no_database():
        raise AssertionError("Database access is forbidden in web boundary tests")
        yield  # make this a dependency generator

    application.dependency_overrides[get_session] = no_database

    @application.post("/api/test-write")
    async def write(request: Request):
        application.state.writes.append(await request.body())
        return {"saved": True}

    return application


@pytest.mark.parametrize(
    "path,auth,expected",
    [
        ("/api/health", None, 401),
        ("/api/health", ("owner", "test-password"), 200),
        ("/api/missing", ("owner", "test-password"), 404),
        ("/api/explode", ("owner", "test-password"), 500),
    ],
)
@pytest.mark.asyncio
async def test_public_security_headers_cover_errors_and_success(public_app, path, auth, expected):
    @public_app.get("/api/explode")
    async def explode():
        raise RuntimeError("synthetic-private-database-and-token-detail")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app), base_url="https://example.test"
    ) as client:
        response = await client.get(path, auth=auth)
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in response.headers
    csp = response.headers["content-security-policy"]
    assert "script-src 'self';" in csp
    assert "style-src 'self' 'unsafe-inline';" in csp
    assert "connect-src 'self';" in csp
    assert "frame-ancestors 'none';" in csp
    assert "object-src 'none';" in csp
    assert "base-uri 'none';" in csp
    assert "synthetic-private" not in response.text
    if expected == 500:
        assert response.json() == {"detail": "Internal server error"}


@pytest.mark.asyncio
async def test_authenticator_errors_are_sanitized_by_outer_boundary(public_app, monkeypatch):
    import app.security as security

    def explode(*args):
        raise RuntimeError("synthetic-secret-hash-detail")

    monkeypatch.setattr(security, "verify_password", explode)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.get("/api/health")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
@pytest.mark.asyncio
async def test_public_documentation_disabled(public_app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.get(path)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/health"),
        ("GET", "/api/orders"),
        ("POST", "/api/test-write"),
        ("GET", "/docs"),
        ("GET", "/redoc"),
        ("GET", "/openapi.json"),
        ("GET", "/"),
        ("GET", "/assets/app.js"),
        ("GET", "/api/unknown"),
    ],
)
@pytest.mark.asyncio
async def test_public_all_routes_require_basic_auth(public_app, method, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app), base_url="https://example.test"
    ) as client:
        for headers in ({}, {"Authorization": "Basic not-base64"}):
            response = await client.request(
                method, path, headers={"Origin": "https://example.test", **headers}
            )
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")
        response = await client.request(
            method, path, auth=("owner", "wrong"), headers={"Origin": "https://example.test"}
        )
        assert response.status_code == 401
        assert not public_app.state.writes


@pytest.mark.asyncio
async def test_valid_basic_auth_reads_writes_and_hashing_is_off_event_loop(public_app, monkeypatch):
    import threading

    import app.security as security

    threads = []
    original = security.verify_password

    def verify(password, encoded):
        threads.append(threading.get_ident())
        return original(password, encoded)

    monkeypatch.setattr(security, "verify_password", verify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        assert (await client.get("/api/health")).status_code == 200
        response = await client.post(
            "/api/test-write", content=b"ok", headers={"Origin": "https://example.test"}
        )
        assert response.status_code == 200
    assert public_app.state.writes == [b"ok"]
    assert threads and all(thread != threading.get_ident() for thread in threads)


@pytest.mark.parametrize(
    "base_url,headers",
    [
        ("http://example.test", {}),
        ("http://example.test", {"X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1"}),
        ("https://evil.test", {}),
        ("https://evil.test", {"X-Forwarded-Host": "example.test"}),
        ("https://example.test", [("Host", "example.test"), ("Host", "evil.test")]),
    ],
)
@pytest.mark.asyncio
async def test_public_rejects_wrong_authority_before_auth(public_app, base_url, headers):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app), base_url=base_url
    ) as client:
        response = await client.get("/api/health", headers=headers)
    assert response.status_code == 400
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize("peer,expected", [("127.0.0.1", 200), ("198.51.100.9", 400)])
@pytest.mark.asyncio
async def test_forwarded_scheme_only_trusted_by_uvicorn_loopback(public_app, peer, expected):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    proxied = ProxyHeadersMiddleware(public_app, trusted_hosts=["127.0.0.1"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxied, client=(peer, 1234)),
        base_url="http://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.get(
            "/api/health",
            headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "198.51.100.42"},
        )
    assert response.status_code == expected


@pytest.mark.parametrize(
    "peer,expected",
    [
        ("127.0.0.1", 200),
        ("::1", 200),
        ("testclient", 403),
        ("test", 403),
        (None, 403),
        ("::ffff:192.168.1.20", 403),
        ("198.51.100.9", 403),
        ("192.168.1.20", 403),
        ("localhost", 403),
        ("127.0.0.1.evil.test", 403),
    ],
)
@pytest.mark.asyncio
async def test_local_mode_uses_peer_address_not_request_hostname(tmp_path, peer, expected):
    from app.main import create_app

    application = create_app(Settings(_env_file=None, frontend_dist=tmp_path / "absent"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=(peer, 1234)),
        base_url="http://localhost",
    ) as client:
        response = await client.get("/api/health", headers={"X-Forwarded-For": "127.0.0.1"})
    assert response.status_code == expected


def test_scrypt_hash_is_salted_and_verifies_only_correct_password():
    assert importlib.util.find_spec("app.security") is not None, "security module missing"
    from app.security import hash_password, verify_password

    encoded = hash_password("synthetic-test-password")
    algorithm, salt, derived = encoded.split("$")
    assert algorithm == "scrypt"
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(derived)) == 32
    assert encoded != hash_password("synthetic-test-password")
    assert verify_password("synthetic-test-password", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("wrong", "scrypt$bad$bad")
    assert not verify_password("wrong", "plaintext")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT", "CUSTOM"])
@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://evil.test",
        "http://example.test",
        "https://example.test/",
        "https://example.test:443",
    ],
)
@pytest.mark.asyncio
async def test_unsafe_methods_need_exact_origin(public_app, method, origin):
    headers = {"Origin": origin} if origin is not None else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.request(method, "/api/test-write", headers=headers)
    assert response.status_code == 403
    assert not public_app.state.writes


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST"])
@pytest.mark.asyncio
async def test_fetch_metadata_rejects_cross_site_even_with_credentials(public_app, method):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.request(
            method,
            "/api/test-write",
            headers={
                "Origin": "https://example.test",
                "Sec-Fetch-Site": "cross-site",
            },
        )
    assert response.status_code == 403
    assert not public_app.state.writes


@pytest.mark.parametrize(
    "headers",
    [
        [("Origin", "https://example.test"), ("Origin", "https://example.test")],
        [
            ("Origin", "https://example.test"),
            ("Sec-Fetch-Site", "same-origin"),
            ("Sec-Fetch-Site", "cross-site"),
        ],
    ],
)
@pytest.mark.asyncio
async def test_duplicate_browser_security_headers_fail_closed(public_app, headers):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.post("/api/test-write", headers=headers)
    assert response.status_code == 403
    assert not public_app.state.writes


@pytest.mark.asyncio
async def test_bad_passwords_are_throttled_and_recover_after_window(public_app, monkeypatch):
    import time

    import app.security as security

    clock = [time.monotonic()]
    monkeypatch.setattr(security, "monotonic", lambda: clock[0], raising=False)
    calls = []
    original = security.verify_password

    def verify(password, encoded):
        calls.append(True)
        return original(password, encoded)

    monkeypatch.setattr(security, "verify_password", verify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "wrong"),
    ) as client:
        responses = [await client.get("/api/health") for _ in range(12)]
        assert responses[0].status_code == 401
        assert responses[-1].status_code == 429
        assert 0 < int(responses[-1].headers["retry-after"]) <= 60
        assert responses[-1].headers["cache-control"] == "no-store"
        assert len(calls) <= 5
        clock[0] += 61
        assert (await client.get("/api/health", auth=("owner", "test-password"))).status_code == 200


@pytest.mark.asyncio
async def test_normal_page_loads_use_bounded_success_cache_without_lockout(public_app, monkeypatch):
    import app.security as security

    calls = []
    original = security.verify_password

    def verify(password, encoded):
        calls.append(True)
        return original(password, encoded)

    monkeypatch.setattr(security, "verify_password", verify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app), base_url="https://example.test"
    ) as client:
        for _ in range(40):
            assert (await client.get("/api/health")).status_code == 401
        assert calls == []  # Missing credentials never allocate scrypt work.
        for _ in range(80):
            assert (
                await client.get("/api/health", auth=("owner", "test-password"))
            ).status_code == 200
        assert len(calls) == 1
        for _ in range(12):
            await client.get("/api/health", auth=("owner", "wrong"))
        # Already authenticated assets are not locked out by a same-IP attacker.
        assert (await client.get("/api/health", auth=("owner", "test-password"))).status_code == 200


@pytest.mark.asyncio
async def test_parallel_auth_work_is_bounded(public_app, monkeypatch):
    import asyncio
    import threading

    import app.security as security

    release = threading.Event()
    entered = []

    def verify(*args):
        entered.append(True)
        assert release.wait(5)
        return False

    monkeypatch.setattr(security, "verify_password", verify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "wrong"),
    ) as client:
        tasks = [asyncio.create_task(client.get("/api/health")) for _ in range(12)]
        try:
            for _ in range(100):
                if sum(task.done() for task in tasks) >= 10:
                    break
                await asyncio.sleep(0.005)
            assert len(entered) <= 2
            assert sum(task.done() for task in tasks) >= 10
        finally:
            release.set()
            responses = await asyncio.gather(*tasks)
    assert sum(response.status_code == 429 for response in responses) >= 10


@pytest.mark.parametrize("declared", [None, "1", str(10 * 1024 * 1024 + 1)])
@pytest.mark.asyncio
async def test_oversized_stream_is_rejected_before_parser_or_handler(
    public_app, monkeypatch, declared
):
    from fastapi import File, UploadFile
    from starlette.formparsers import MultiPartParser

    entered = []

    async def forbidden_parser(*args):
        entered.append("parser")
        raise AssertionError("Oversized multipart reached parser")

    monkeypatch.setattr(MultiPartParser, "parse", forbidden_parser)

    @public_app.post("/api/test-upload")
    async def upload(file: UploadFile = File(...)):
        entered.append("handler")
        return {"ok": True}

    async def content():
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    headers = {
        "Origin": "https://example.test",
        "Content-Type": "multipart/form-data; boundary=test",
    }
    if declared is not None:
        headers["Content-Length"] = declared
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        request = client.build_request(
            "POST", "/api/test-upload", content=content(), headers=headers
        )
        if declared is not None:
            request.headers.pop("transfer-encoding", None)
        response = await client.send(request)
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert not entered


@pytest.mark.asyncio
async def test_body_limit_also_applies_to_handlers_that_never_read_body(public_app):
    async def content():
        yield b"x" * (10 * 1024 * 1024 + 1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.request("GET", "/api/health", content=content())
    assert response.status_code == 413


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.asyncio
async def test_body_at_exact_limit_is_replayed_without_loss(public_app, streamed):
    body = b"x" * (10 * 1024 * 1024)

    async def content():
        for start in range(0, len(body), 65536):
            yield body[start : start + 65536]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.post(
            "/api/test-write",
            content=content() if streamed else body,
            headers={"Origin": "https://example.test"},
        )
    assert response.status_code == 200
    assert public_app.state.writes == [body]


@pytest.mark.parametrize("lengths", [["-1"], ["not-a-number"], ["1", "1"], ["0"]])
@pytest.mark.asyncio
async def test_invalid_or_mismatched_content_length_is_rejected(public_app, lengths):
    headers = [("Origin", "https://example.test")] + [
        ("Content-Length", value) for value in lengths
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.post("/api/test-write", content=b"xx", headers=headers)
    assert response.status_code == 400
    assert not public_app.state.writes


@pytest.fixture
def spa_app(public_config):
    from app.database import get_session
    from app.main import create_app

    dist = public_config.frontend_dist
    dist.mkdir()
    (dist / "index.html").write_text('<html><div id="root">synthetic SPA</div></html>')
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text('console.log("synthetic")')
    (dist / ".secret").write_text("synthetic-private-content")
    outside = dist.parent / "outside.txt"
    outside.write_text("synthetic-private-content")
    (dist / "leaked.txt").symlink_to(outside)
    application = create_app(public_config)

    async def no_database():
        raise AssertionError("Database access is forbidden in SPA tests")
        yield

    application.dependency_overrides[get_session] = no_database
    return application


@pytest.mark.parametrize("path", ["/", "/portfolio", "/orders/history", "/instruments/42"])
@pytest.mark.asyncio
async def test_spa_serves_deep_links_from_configured_directory(spa_app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=spa_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.get(path, headers={"Accept": "text/html"})
        head = await client.head(path, headers={"Accept": "text/html"})
    assert response.status_code == head.status_code == 200
    assert "synthetic SPA" in response.text
    assert head.content == b""
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/api",
        "/api/unknown",
        "/assets",
        "/assets/missing",
        "/assets/missing.js",
        "/missing.css",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/.secret",
        "/leaked.txt",
        "/%2e%2e/outside.txt",
        "/assets/%2e%2e/index.html",
        "/assets%5c..%5cindex.html",
        "/%252e%252e/outside.txt",
        "/%00",
        "/missing.js/nested",
    ],
)
@pytest.mark.asyncio
async def test_spa_never_masks_api_assets_or_unsafe_paths(spa_app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=spa_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "synthetic SPA" not in response.text
    assert "synthetic-private" not in response.text


@pytest.mark.asyncio
async def test_spa_assets_require_auth_and_fetches_do_not_fallback(spa_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=spa_app), base_url="https://example.test"
    ) as client:
        assert (await client.get("/assets/app.js")).status_code == 401
        response = await client.get("/assets/app.js", auth=("owner", "test-password"))
        assert response.status_code == 200
        assert response.text == 'console.log("synthetic")'
        assert (
            await client.get("/not-a-navigation", auth=("owner", "test-password"))
        ).status_code == 404
        assert (
            await client.post(
                "/portfolio",
                auth=("owner", "test-password"),
                headers={"Origin": "https://example.test"},
            )
        ).status_code == 405


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"public_origin": "http://example.test"},
        {"public_origin": "https://example.test/"},
        {"public_origin": "https://user@example.test"},
        {"public_origin": "https://example.test?query=1"},
        {"public_origin": "https://example.test#fragment"},
        {"public_origin": "https://example.test:99999"},
        {"public_origin": "https://example.test:"},
        {"public_origin": "https://example.test:443"},
        {"public_origin": "https://-example.test"},
        {"public_origin": "https://example..test"},
        {"public_origin": "https://."},
        {"auth_username": ""},
        {"auth_username": "bad:user"},
        {"auth_username": "a" * 257},
        {"auth_username": "bad\nuser"},
        {"auth_password_hash": "scrypt$00$00"},
        {"auth_password_hash": "plaintext-do-not-print"},
    ],
)
@pytest.mark.asyncio
async def test_public_startup_fails_before_database_for_invalid_config(overrides, monkeypatch):
    import app.main as main
    from app.security import hash_password

    assert callable(getattr(main, "create_app", None)), "isolated app factory missing"
    values = {"deployment_mode": "public"}
    if overrides:
        values.update(
            public_origin="https://example.test",
            auth_username="owner",
            auth_password_hash=hash_password("test-password"),
        )
        values.update(overrides)
    config = Settings(_env_file=None, **values)
    called = []

    async def forbidden_database():
        called.append(True)

    monkeypatch.setattr(main, "init_db", forbidden_database)
    application = main.create_app(config)
    with pytest.raises(RuntimeError, match="Invalid public security configuration") as error:
        async with application.router.lifespan_context(application):
            pass
    assert not called
    assert "plaintext-do-not-print" not in str(error.value)


def test_security_settings_default_local_and_redact_hash():
    config = Settings(_env_file=None, auth_password_hash="test-only-not-a-real-hash")
    assert getattr(config, "deployment_mode", None) == "local"
    assert config.auth_password_hash.get_secret_value() == "test-only-not-a-real-hash"
    assert "test-only-not-a-real-hash" not in repr(config)
    assert config.max_request_body_bytes == 10 * 1024 * 1024
    assert config.frontend_dist == Path(__file__).resolve().parents[2] / "frontend" / "dist"


def test_setting_errors_do_not_echo_inputs_and_username_is_redacted():
    from pydantic import ValidationError

    config = Settings(_env_file=None, auth_username="private-user")
    assert "private-user" not in repr(config)
    assert config.auth_username.get_secret_value() == "private-user"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, deployment_mode="secret-accidentally-in-wrong-field")
    assert "secret-accidentally-in-wrong-field" not in str(error.value)


@pytest.mark.parametrize("limit", [0, -1, 10 * 1024 * 1024 + 1])
def test_body_limit_cannot_disable_or_raise_hard_ceiling(limit):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_request_body_bytes=limit)


@pytest.mark.parametrize(
    "origin", ["https://example.test", "https://example.test:8443", "https://[::1]:8443"]
)
@pytest.mark.asyncio
async def test_valid_public_startup_runs_only_mocked_migration(public_config, origin, monkeypatch):
    import app.main as main

    public_config.public_origin = origin
    called = []

    async def migration():
        called.append(True)

    monkeypatch.setattr(main, "init_db", migration)
    application = main.create_app(public_config)
    async with application.router.lifespan_context(application):
        pass
    assert called == [True]


@pytest.mark.asyncio
async def test_websockets_are_fail_closed(public_app):
    from fastapi import WebSocket

    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    @public_app.websocket("/api/test-ws")
    async def websocket(websocket: WebSocket):
        raise AssertionError("WebSocket reached unauthenticated endpoint")

    await public_app(
        {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "path": "/api/test-ws",
            "headers": [],
            "scheme": "wss",
            "query_string": b"",
            "root_path": "",
        },
        receive,
        send,
    )
    assert sent == [{"type": "websocket.close", "code": 1008}]


@pytest.mark.asyncio
async def test_global_auth_throttle_has_bounded_state_under_rotating_peers(public_app, monkeypatch):
    import app.security as security

    now = [1000.0]
    calls = []
    monkeypatch.setattr(security, "monotonic", lambda: now[0])

    def verify(*args):
        calls.append(True)
        return False

    monkeypatch.setattr(security, "verify_password", verify)
    for index in range(100):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=public_app, client=(f"198.51.100.{index}", 1234)),
            base_url="https://example.test",
            auth=("owner", "wrong"),
        ) as client:
            response = await client.get("/api/health")
            assert response.status_code == (401 if index < 30 else 429)
    assert len(calls) == 30
    assert len(public_app.middleware_stack._attempts) == 30
    now[0] += 61
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "wrong"),
    ) as client:
        assert (await client.get("/api/health")).status_code == 401
    assert len(public_app.middleware_stack._attempts) == 1


@pytest.mark.asyncio
async def test_cancelled_requests_do_not_free_running_scrypt_slots(public_app, monkeypatch):
    import asyncio
    import threading

    import app.security as security

    entered = []
    release = threading.Event()

    def verify(*args):
        entered.append(True)
        assert release.wait(5)
        return False

    monkeypatch.setattr(security, "verify_password", verify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "wrong"),
    ) as client:
        tasks = [asyncio.create_task(client.get("/api/health")) for _ in range(2)]
        try:
            for _ in range(200):
                if len(entered) == 2:
                    break
                await asyncio.sleep(0.005)
            assert len(entered) == 2
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            assert (await client.get("/api/health")).status_code == 429
            assert len(entered) == 2
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            for _ in range(200):
                if public_app.middleware_stack._hashing == 0:
                    break
                await asyncio.sleep(0.005)
        assert public_app.middleware_stack._hashing == 0
        assert (await client.get("/api/health")).status_code == 401


@pytest.mark.asyncio
async def test_small_multipart_reaches_real_parser(public_app):
    from fastapi import File, UploadFile

    @public_app.post("/api/test-upload-small")
    async def upload(file: UploadFile = File(...)):
        return {"content": (await file.read()).decode()}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        response = await client.post(
            "/api/test-upload-small",
            files={"file": ("synthetic.txt", b"small")},
            headers={"Origin": "https://example.test"},
        )
    assert response.status_code == 200
    assert response.json() == {"content": "small"}


@pytest.mark.asyncio
async def test_public_mode_never_triggers_broker_sync_from_the_web(public_app, monkeypatch):
    import app.routers.sync as sync_router

    async def forbidden(*args, **kwargs):
        raise AssertionError("Public web requests must not start a broker sync")

    monkeypatch.setattr(sync_router, "run_sync_all", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=public_app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        for query in ("", "?fetch=false"):
            response = await client.post(
                f"/api/sync/all{query}", headers={"Origin": "https://example.test"}
            )
            assert response.status_code == 403
            assert "schedule" in response.json()["detail"]
