"""Route rehearsal uses disposable SQLite only, no production lifespan."""
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import verify_analysis_ui as rehearsal
from ui_contracts import allowed_gets


async def test_auth_baseline_wrapper_does_not_open_production_auth_store(tmp_path):
    import sqlite3

    from app.config import Settings
    from app.security import hash_password
    db = tmp_path / 'empty.db'
    sqlite3.connect(db).close()
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('synthetic')
    config = Settings(_env_file=None, deployment_mode='public', public_origin='https://example.test',
                      auth_username='fixture', auth_password_hash=hash_password('synthetic-only'))
    app, engine = rehearsal.create_app(db, tmp_path, security_config=config)
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


def test_zero_event_browser_journey_is_explicit(tmp_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
        try:
            # Deterministic zero-event fixture, never a broker/order fabrication.
            def fixture(route):
                if '/api/orders/page' in route.request.url:
                    route.fulfill(json={'items': [], 'total_count': 0, 'has_more': False})
                else:
                    route.fulfill(content_type='text/html', body='''<main><div role="region" aria-label="Order results">No orders on this page. Refine your filters or go back.</div><button disabled>Next page</button></main><script>fetch('/api/orders/page')</script>''')
            result = rehearsal.verify_zero_event_navigation(browser, 'http://fixture.test', route_fixture=fixture)
            assert result['failures'] == []
            assert result['checks'][0]['fixture'] == 'explicit-zero-event'
        finally:
            browser.close()


async def test_rehearsal_includes_every_audited_get_without_startup(tmp_path, monkeypatch):
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
    app, engine = rehearsal.create_app(db, dist)
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
