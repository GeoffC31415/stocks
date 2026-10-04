"""Journal diagnostics use synthetic responses and never expose provider data."""

import ast
import inspect
import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, ImportBatch, OrderImportBatch
from app.routers import trading212 as router
from app.services import sync_runner as runner
from app.services import trading212 as service
from app.services.trading212 import Trading212Client, Trading212DataError


def test_every_provider_rejection_has_a_source_owned_allowlisted_code():
    tree = ast.parse(inspect.getsource(service))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"Trading212DataError", "Trading212CurrencyError"}:
            continue
        codes = [keyword.value for keyword in node.keywords if keyword.arg == "code"]
        assert codes, f"Unclassified rejection at line {node.lineno}"
        assert isinstance(codes[0], ast.Constant)
        assert codes[0].value in service.DIAGNOSTIC_CODES
        assert codes[0].value != "invalid_data"


@pytest.fixture(autouse=True)
def journal_capture(monkeypatch, caplog):
    # Migration tests run Alembic fileConfig, which disables existing loggers.
    # Scope restoration to this test so collection order cannot hide diagnostics.
    monkeypatch.setattr(runner.logger, "disabled", False)
    caplog.set_level("ERROR", logger=runner.__name__)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


class Reader:
    async def fetch_positions(self):
        return []

    async def fetch_account_summary(self):
        return {
            "currency": "GBP",
            "cash": {
                "availableToTrade": 0,
                "inPies": 0,
                "reservedForOrders": 0,
            },
        }

    async def fetch_historical_orders(self):
        return []

    async def fetch_transactions(self):
        return [{"type": "PRIVATE_PROVIDER_SENTINEL"}]


async def run(db, tmp_path, monkeypatch, reader):
    monkeypatch.setattr(runner.settings, "trading212_api_key", SecretStr("SYNTHETIC_KEY"))
    monkeypatch.setattr(runner.settings, "trading212_api_secret", SecretStr("SYNTHETIC_SECRET"))
    monkeypatch.setattr(runner.settings, "sync_status_dir", tmp_path / "public")
    monkeypatch.setenv("INVOCATION_ID", "a" * 32)
    monkeypatch.setattr(router, "get_trading212_client", lambda: reader)
    return await runner.run_sync_all(db, inbox=tmp_path / "inbox")


async def test_unsupported_cash_type_is_correlated_without_payload(
    db,
    tmp_path,
    monkeypatch,
    caplog,
):
    report = await run(db, tmp_path, monkeypatch, Reader())
    assert report.steps[-1].status == "failed"
    assert "code=unsupported_cash_transaction_type" in caplog.text
    assert "endpoint=transactions phase=import" in caplog.text
    assert "invocation_id=" + "a" * 32 in caplog.text
    assert "PRIVATE_PROVIDER_SENTINEL" not in caplog.text
    assert "SYNTHETIC_KEY" not in caplog.text
    assert "SYNTHETIC_SECRET" not in caplog.text
    records = [r for r in caplog.records if r.name == runner.__name__]
    assert len(records) == 1
    assert records[0].exc_info is None
    public = json.loads((tmp_path / "public/last-sync.json").read_text())
    assert public["steps"][-1]["detail"] is None
    assert "unsupported_cash_transaction_type" not in json.dumps(public)
    assert await db.scalar(select(func.count()).select_from(ImportBatch)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderImportBatch)) == 0


@pytest.mark.parametrize(
    ("endpoint", "payload", "status", "code", "phase"),
    [
        ("positions", {}, 200, "invalid_positions_response", "fetch"),
        ("account_summary", [], 200, "invalid_account_summary", "fetch"),
        ("account_summary", {}, 403, "account_summary_forbidden", "import"),
        ("account_summary", {"currency": "GBP", "cash": {}}, 200, "invalid_cash_values", "import"),
        ("account_summary", {"currency": "USD"}, 200, "non_gbp_currency", "import"),
        ("orders", {}, 200, "invalid_order_history_response", "fetch"),
        (
            "orders",
            {"items": [], "nextPagePath": "https://PRIVATE_URL_SENTINEL/secret"},
            200,
            "invalid_order_pagination",
            "fetch",
        ),
        ("transactions", {}, 200, "invalid_cash_history_response", "fetch"),
        (
            "transactions",
            {"items": [], "nextPagePath": "https://PRIVATE_URL_SENTINEL/secret"},
            200,
            "invalid_cash_pagination",
            "fetch",
        ),
        (
            "transactions",
            {
                "items": [{"type": "DEPOSIT", "dateTime": "PRIVATE_BODY_SENTINEL"}],
                "nextPagePath": None,
            },
            200,
            "invalid_cash_transaction_date",
            "import",
        ),
    ],
)
async def test_known_provider_failures_have_distinct_safe_codes(
    db,
    tmp_path,
    monkeypatch,
    caplog,
    endpoint,
    payload,
    status,
    code,
    phase,
):
    paths = {
        "positions": "/api/v0/equity/positions",
        "account_summary": "/api/v0/equity/account/summary",
        "orders": "/api/v0/equity/history/orders",
        "transactions": "/api/v0/equity/history/transactions",
    }
    defaults = {
        "positions": [],
        "account_summary": await Reader().fetch_account_summary(),
        "orders": {"items": [], "nextPagePath": None},
        "transactions": {"items": [], "nextPagePath": None},
    }

    def transport(request):
        name = next(name for name, path in paths.items() if request.url.path == path)
        return httpx.Response(
            status if name == endpoint else 200,
            json=payload if name == endpoint else defaults[name],
        )

    client = Trading212Client(
        api_key="SYNTHETIC_KEY",
        api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport),
        page_delay=0,
    )
    report = await run(db, tmp_path, monkeypatch, client)
    assert report.steps[-1].status == "failed"
    assert f"code={code}" in caplog.text
    # Snapshot validation consumes both summary and positions in the import phase.
    expected_endpoint = (
        "positions" if endpoint == "account_summary" and phase == "import" else endpoint
    )
    if code == "account_summary_forbidden":
        expected_endpoint = "account_summary"
        assert "http_status=403" in caplog.text
    assert f"endpoint={expected_endpoint} phase={phase}" in caplog.text
    for sentinel in (
        "PRIVATE_URL_SENTINEL",
        "PRIVATE_BODY_SENTINEL",
        "SYNTHETIC_KEY",
        "SYNTHETIC_SECRET",
    ):
        assert sentinel not in caplog.text
        assert sentinel not in json.dumps(report.to_json())
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("code", ["PRIVATE_CODE_SENTINEL", ["PRIVATE_CODE_SENTINEL"], None])
async def test_unknown_exception_metadata_never_enters_logs(
    db,
    tmp_path,
    monkeypatch,
    caplog,
    code,
):
    class HostileReader(Reader):
        async def fetch_positions(self):
            exc = Trading212DataError("PRIVATE_EXCEPTION_SENTINEL")
            exc.code = code
            exc.t212_endpoint = "PRIVATE_URL_SENTINEL"
            exc.t212_phase = "PRIVATE_PHASE_SENTINEL"
            raise exc from ValueError("PRIVATE_CAUSE_SENTINEL")

    report = await run(db, tmp_path, monkeypatch, HostileReader())
    assert "code=invalid_data endpoint=positions phase=fetch" in caplog.text
    assert "PRIVATE_" not in caplog.text
    assert "PRIVATE_" not in json.dumps(report.to_json())
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    ("failure", "code", "status"),
    [
        ("permission", "http_permission_denied", "403"),
        ("rate_limit", "http_rate_limited", "429"),
        ("http", "http_error", "502"),
        ("network", "transport_error", "unavailable"),
        ("unexpected", "unexpected_error", "unavailable"),
        ("invalid_json", "invalid_json_response", "unavailable"),
        ("retry_header", "invalid_retry_after", "unavailable"),
        ("retry_budget", "retry_after_budget_exceeded", "unavailable"),
    ],
)
async def test_transport_failures_are_safe_and_correlated(
    db,
    tmp_path,
    monkeypatch,
    caplog,
    failure,
    code,
    status,
):
    private_url = "https://PRIVATE_URL_SENTINEL/?api_key=PRIVATE_SECRET_SENTINEL"

    def transport(request):
        hostile_request = httpx.Request("GET", private_url)
        if failure in {"permission", "rate_limit", "http"}:
            response = httpx.Response(
                int(status), request=hostile_request, text="PRIVATE_BODY_SENTINEL"
            )
            raise httpx.HTTPStatusError(
                "PRIVATE_EXCEPTION_SENTINEL", request=hostile_request, response=response
            )
        if failure == "network":
            raise httpx.RequestError("PRIVATE_EXCEPTION_SENTINEL", request=hostile_request)
        if failure == "unexpected":
            raise RuntimeError("PRIVATE_EXCEPTION_SENTINEL")
        if failure == "invalid_json":
            return httpx.Response(200, text="PRIVATE_BODY_SENTINEL")
        retry = "PRIVATE_HEADER_SENTINEL" if failure == "retry_header" else "9" * 20
        return httpx.Response(429, text="PRIVATE_BODY_SENTINEL", headers={"Retry-After": retry})

    client = Trading212Client(
        api_key="SYNTHETIC_KEY",
        api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport),
        page_delay=0,
    )
    report = await run(db, tmp_path, monkeypatch, client)
    assert report.steps[-1].status == "failed"
    assert f"code={code} endpoint=positions phase=fetch" in caplog.text
    assert f"http_status={status}" in caplog.text
    assert "invocation_id=" + "a" * 32 in caplog.text
    assert "PRIVATE_" not in caplog.text
    assert "PRIVATE_" not in json.dumps(report.to_json())
    assert all(record.exc_info is None for record in caplog.records)


async def test_invocation_is_captured_at_start_not_failure(
    db,
    tmp_path,
    monkeypatch,
    caplog,
):
    class ChangesEnvironment(Reader):
        async def fetch_transactions(self):
            monkeypatch.setenv("INVOCATION_ID", "b" * 32)
            return await super().fetch_transactions()

    report = await run(db, tmp_path, monkeypatch, ChangesEnvironment())
    assert report.invocation_id == "a" * 32
    assert "invocation_id=" + "a" * 32 in caplog.text
    assert "b" * 32 not in caplog.text


async def test_diagnostic_annotation_cannot_prevent_owner_rollback(
    db,
    tmp_path,
    monkeypatch,
    caplog,
):
    class NoMetadataError(Trading212DataError):
        def __setattr__(self, name, value):
            if name.startswith("t212_"):
                raise RuntimeError("PRIVATE_ANNOTATION_SENTINEL")
            super().__setattr__(name, value)

    async def fails_after_import(*args, **kwargs):
        raise NoMetadataError("PRIVATE_EXCEPTION_SENTINEL")

    monkeypatch.setattr(router, "sync_cash_history", fails_after_import)
    report = await run(db, tmp_path, monkeypatch, Reader())
    assert report.steps[-1].status == "failed"
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(ImportBatch)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderImportBatch)) == 0
    assert "code=invalid_data" in caplog.text
    assert "PRIVATE_" not in caplog.text


async def test_cli_restores_journal_logger_after_migration_configuration(
    db,
    tmp_path,
    monkeypatch,
    caplog,
    capsys,
):
    from argparse import Namespace
    from contextlib import asynccontextmanager

    from app import sync_cli

    async def migration_logging():
        # Same side effect as Alembic's logging.config.fileConfig at startup.
        runner.logger.disabled = True

    @asynccontextmanager
    async def sessions():
        yield db

    monkeypatch.setattr(sync_cli, "init_db", migration_logging)
    monkeypatch.setattr(sync_cli, "SessionLocal", sessions)
    monkeypatch.setattr(runner.settings, "sync_inbox", tmp_path / "inbox")
    monkeypatch.setattr(runner.settings, "trading212_api_key", SecretStr("SYNTHETIC_KEY"))
    monkeypatch.setattr(runner.settings, "trading212_api_secret", SecretStr("SYNTHETIC_SECRET"))
    monkeypatch.setattr(router, "get_trading212_client", Reader)
    args = Namespace(
        no_fetch=True, include_downloads=False, no_trading212=False, dry_run=False, json=True
    )
    assert await sync_cli._run_locked(args) == 1
    assert "code=unsupported_cash_transaction_type" in caplog.text
    assert "PRIVATE_" not in caplog.text
    assert "PRIVATE_" not in capsys.readouterr().out


async def test_outer_sync_deadline_is_logged_without_exception_details(
    db,
    tmp_path,
    monkeypatch,
    caplog,
):
    import asyncio

    class HangingReader(Reader):
        async def fetch_positions(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(runner, "FETCH_TIMEOUT_SECONDS", 0.01)
    report = await run(db, tmp_path, monkeypatch, HangingReader())
    assert report.steps[-1].status == "failed"
    assert "code=sync_timeout endpoint=sync phase=deadline" in caplog.text
    assert "invocation_id=" + "a" * 32 in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("invocation_id", [None, "PRIVATE_INVOCATION_SENTINEL", "A" * 32])
async def test_sink_revalidates_all_metadata_and_invocation(
    db,
    monkeypatch,
    caplog,
    invocation_id,
):
    class PRIVATE_CLASS_SENTINEL(Trading212DataError):
        def __str__(self):
            raise AssertionError("Exception formatting must never be attempted")

    async def hostile_sync(*args, **kwargs):
        exc = PRIVATE_CLASS_SENTINEL("PRIVATE_EXCEPTION_SENTINEL")
        exc.code = ["PRIVATE_CODE_SENTINEL"]
        vars(exc).update(t212_endpoint="PRIVATE_URL_SENTINEL", t212_phase="PRIVATE_PHASE_SENTINEL")
        raise exc

    monkeypatch.setattr(runner, "_trading212_configured", lambda: True)
    monkeypatch.setattr(router, "get_trading212_client", Reader)
    monkeypatch.setattr(router, "run_trading212_sync", hostile_sync)
    result = await runner._trading212_step(db, invocation_id=invocation_id)
    assert result.detail == "Trading212DataError"
    assert "code=invalid_data endpoint=sync phase=unknown invocation_id=unavailable" in caplog.text
    assert "PRIVATE_" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("kind", ["unexpected", "validation", "permission"])
def test_api_error_logs_only_safe_codes_and_never_exception_text(kind, caplog, monkeypatch):
    monkeypatch.setattr(router.logger, "disabled", True)
    caplog.set_level("ERROR", logger=router.__name__)
    if kind == "unexpected":
        exc = RuntimeError("PRIVATE_SECRET_SENTINEL")
        expected = "unexpected_error"
    elif kind == "validation":
        exc = Trading212DataError("PRIVATE_SECRET_SENTINEL")
        expected = "invalid_data"
    else:
        exc = Trading212DataError("PRIVATE_SECRET_SENTINEL", code="account_summary_forbidden")
        expected = "account_summary_forbidden"
    result = router._provider_error(exc)
    assert f"code={expected}" in caplog.text
    assert "PRIVATE_SECRET_SENTINEL" not in caplog.text
    assert "PRIVATE_SECRET_SENTINEL" not in result.detail
    assert all(record.exc_info is None for record in caplog.records)
    if kind == "permission":
        assert "read-only account permission" in result.detail


@pytest.mark.parametrize("operation", ["cash", "orders", "portfolio"])
async def test_standalone_routes_log_source_owned_endpoint(operation, db, monkeypatch, caplog):
    from fastapi import HTTPException

    endpoint = {"cash": "transactions", "orders": "orders", "portfolio": "positions"}[operation]
    function = {"cash": "sync_cash_history", "orders": "sync_order_history", "portfolio": "sync_portfolio_snapshot"}[operation]
    route = {"cash": router.sync_trading212_cash_flows, "orders": router.sync_trading212_orders, "portfolio": router.sync_trading212_portfolio}[operation]

    async def denied(*args, **kwargs):
        request = httpx.Request("GET", "https://PRIVATE_URL_SENTINEL")
        raise httpx.HTTPStatusError("PRIVATE_SECRET_SENTINEL", request=request, response=httpx.Response(403, request=request))

    monkeypatch.setattr(router, function, denied)
    monkeypatch.setattr(router.logger, "disabled", True)
    caplog.set_level("ERROR", logger=router.__name__)
    with pytest.raises(HTTPException):
        await route(session=db, client=Reader())
    assert f"endpoint={endpoint} phase=fetch http_status=403" in caplog.text
    assert "code=http_permission_denied" in caplog.text
    assert "PRIVATE_" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
