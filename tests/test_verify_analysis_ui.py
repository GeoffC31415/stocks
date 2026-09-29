"""Route rehearsal uses disposable SQLite only, no production lifespan."""
import os
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import verify_analysis_ui as rehearsal
from ui_contracts import allowed_gets


@pytest.fixture
def isolated_rehearsal(monkeypatch):
    """Adapt the CLI-only bootstrap for calls inside the pytest process."""
    def create_app(*args, **kwargs):
        # The CLI bootstrap intentionally overrides inherited settings before
        # imports. Register those writes so success AND exceptions restore the
        # exact caller environment, rather than deleting inherited values.
        with monkeypatch.context() as scope:
            scope.setenv('PORTFOLIO_DATABASE_URL', 'sqlite+aiosqlite:///:memory:')
            scope.setenv('PORTFOLIO_DEPLOYMENT_MODE', 'local')
            scope.setattr(sys, 'path', sys.path.copy())
            return rehearsal.create_app(*args, **kwargs)
    return create_app


@pytest.mark.parametrize('inherited_environment', [False, True])
@pytest.mark.parametrize('failed_preview', [False, True])
async def test_preview_preserves_environment_and_process_database(
    tmp_path, monkeypatch, isolated_rehearsal, inherited_environment, failed_preview,
):
    from app import database
    from app.config import Settings
    from app.main import create_app
    from sqlalchemy.engine import make_url

    keys = ('PORTFOLIO_DATABASE_URL', 'PORTFOLIO_DEPLOYMENT_MODE')
    if inherited_environment:
        monkeypatch.setenv(keys[0], str(database.engine.url))
        monkeypatch.setenv(keys[1], 'local')
    else:
        for key in keys:
            monkeypatch.delenv(key, raising=False)
    before_environment = {key: os.environ.get(key) for key in keys}
    before_path = sys.path.copy()
    before_engine = database.engine
    before_sessions = database.SessionLocal
    before_settings = database.settings
    config = Settings(_env_file=None)
    assert make_url(config.resolved_database_url()) == before_engine.url
    assert make_url(before_settings.resolved_database_url()) == before_engine.url
    assert before_sessions.kw['bind'] is before_engine

    if failed_preview:
        with pytest.raises(RuntimeError, match='does not exist'):
            isolated_rehearsal(tmp_path / 'synthetic.db', tmp_path / 'missing-dist')
    else:
        (tmp_path / 'assets').mkdir()
        (tmp_path / 'index.html').write_text('synthetic')
        _, engine = isolated_rehearsal(tmp_path / 'synthetic.db', tmp_path)
        await engine.dispose()

    assert {key: os.environ.get(key) for key in keys} == before_environment
    assert sys.path == before_path
    assert database.engine is before_engine
    assert database.SessionLocal is before_sessions
    assert database.settings is before_settings
    assert make_url(Settings(_env_file=None).resolved_database_url()) == before_engine.url
    # Exercise the real fail-closed factory after preview (without lifespan or DB IO).
    application = create_app(Settings(_env_file=None, frontend_dist=tmp_path / 'not-built'))
    assert application.state.web_config.resolved_database_url() == config.resolved_database_url()


@pytest.mark.parametrize('name', ['.env', 'backend/.env'])
def test_factory_refuses_dotenv_before_any_application_import(tmp_path, monkeypatch, name):
    import builtins
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('SYNTHETIC_SENTINEL=must-not-be-read')
    monkeypatch.setattr(rehearsal, 'REPO', tmp_path)
    original = builtins.__import__
    imports = []
    def guarded(module, *args, **kwargs):
        if module == 'app' or module.startswith('app.'):
            imports.append(module)
            raise AssertionError('Application imported before dotenv refusal')
        return original(module, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    with pytest.raises(RuntimeError, match='dotenv'):
        rehearsal.create_app(tmp_path / 'absent.db', tmp_path / 'dist')
    assert imports == []


def test_zero_order_prerequisite_checks_database_not_just_filtered_page(tmp_path):
    import sqlite3
    db = tmp_path / 'fixture.db'
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO orders VALUES (1)')
    with pytest.raises(ValueError, match='zero-order'):
        rehearsal.assert_zero_order_database(db)


async def test_auth_baseline_wrapper_does_not_open_production_auth_store(tmp_path, isolated_rehearsal):
    import sqlite3

    from app.config import Settings
    from app.security import hash_password
    db = tmp_path / 'empty.db'
    sqlite3.connect(db).close()
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('synthetic')
    config = Settings(_env_file=None, deployment_mode='public', public_origin='https://example.test',
                      auth_username='fixture', auth_password_hash=hash_password('synthetic-only'))
    app, engine = isolated_rehearsal(db, tmp_path, security_config=config)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://example.test') as client:
            assert (await client.get('/api/health')).status_code == 401
            assert (await client.get('/api/health', auth=('fixture', 'synthetic-only'))).status_code == 200
            assert (await client.post('/api/imports', auth=('fixture', 'synthetic-only'), headers={'Origin': 'https://example.test'})).status_code == 405
        assert not config.auth_database_path
    finally:
        await engine.dispose()


async def test_synthetic_preview_fixture_is_deterministic_zero_event_and_exclusive(tmp_path):
    import synthetic_preview
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    path = tmp_path / 'synthetic.db'
    await synthetic_preview.create_synthetic_database(path)
    engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text('SELECT count(*) FROM orders'))).scalar() == 0
            assert (await connection.execute(text('SELECT count(*) FROM holding_snapshots'))).scalar() == 12
            assert (await connection.execute(text('SELECT DISTINCT account_name FROM instruments ORDER BY account_name'))).scalars().all() == ['Synthetic ISA', 'Synthetic SIPP']
        before = path.read_bytes()
        with pytest.raises(FileExistsError):
            await synthetic_preview.create_synthetic_database(path)
        assert path.read_bytes() == before
    finally:
        await engine.dispose()


def test_zero_event_browser_journey_rejects_populated_orders(tmp_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
        try:
            # Deterministic zero-event fixture, never a broker/order fabrication.
            def fixture(route):
                if '/api/orders/page' in route.request.url:
                    route.fulfill(json={'items': [{'id': 1}], 'total_count': 1, 'has_more': False})
                else:
                    route.fulfill(content_type='text/html', body='''<main><div role="region" aria-label="Order results">No orders on this page. Refine your filters or go back.</div><button disabled>Next page</button></main><script>fetch('/api/orders/page')</script>''')
            result = rehearsal.verify_zero_event_navigation(browser, 'http://fixture.test', route_fixture=fixture)
            assert result['failures']
            assert result['checks'] == []
        finally:
            browser.close()


async def test_rehearsal_includes_every_audited_get_without_startup(tmp_path, monkeypatch, isolated_rehearsal):
    from app import database
    from app.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine
    db = tmp_path / 'fixture.db'
    engine = create_async_engine(f'sqlite+aiosqlite:///{db}')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('synthetic UI')
    async def forbidden():
        raise AssertionError('Production startup migrations prohibited')
    monkeypatch.setattr(database, 'init_db', forbidden)
    app, engine = isolated_rehearsal(db, dist)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/portfolio/summary')).status_code == 200
            assert (await client.get('/api/orders/page')).status_code == 200
            assert (await client.get('/api/health')).json() == {'status': 'ok'}
            assert (await client.post('/api/imports')).status_code == 405
            assert (await client.get('/api/trading212/snapshot')).status_code == 404
        assert rehearsal.audited_route_paths(app) == allowed_gets()
    finally:
        await engine.dispose()
