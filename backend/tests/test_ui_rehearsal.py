"""Safety tests for the harness; only synthetic, temporary SQLite data."""
import importlib
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
harness = importlib.import_module("verify_analysis_ui")
contracts = importlib.import_module("ui_contracts")


def test_browser_allowlist_blocks_mutations_external_hosts_and_unrelated_gets():
    base = "http://127.0.0.1:8123"
    assert contracts.request_allowed("GET", base + "/api/instruments?account_name=ISA", base, "holdings")
    assert not contracts.request_allowed("POST", base + "/api/instruments", base, "holdings")
    assert not contracts.request_allowed("GET", "https://example.com/data", base, "holdings")
    assert not contracts.request_allowed("GET", base + "/api/orders", base, "allocation")
    assert not contracts.request_allowed("GET", base + "/api/market-data/refresh", base, "overview")


@pytest.mark.asyncio
async def test_rehearsal_uses_its_own_read_only_database_and_blocks_writes(tmp_path, monkeypatch):
    from app.database import get_session
    from app.main import app as original

    database = tmp_path / "synthetic.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE evidence (value TEXT)")
        db.execute("INSERT INTO evidence VALUES ('copy-only')")
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("isolated UI")
    app, engine = harness.create_app(database, tmp_path)
    assert app is not original
    assert original.dependency_overrides.get(get_session) is None
    # Verify routing really uses our dependency provider, not original.routes'.
    summary = next(r for r in app.routes if r.path == "/api/portfolio/summary")
    assert summary.dependency_overrides_provider is app
    try:
        async for session in app.dependency_overrides[get_session]():
            assert (await session.execute(text("SELECT value FROM evidence"))).scalar() == "copy-only"
            with pytest.raises(OperationalError, match="readonly"):
                await session.execute(text("DELETE FROM evidence"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/health")).json() == {"status": "ok"}
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                assert (await client.request(method, "/api/imports")).status_code == 405
            assert (await client.get("/api/market-data/refresh")).status_code == 404
    finally:
        await engine.dispose()


def test_child_failure_detected_before_readiness_request(monkeypatch):
    request = Mock()
    monkeypatch.setattr(harness.urllib.request, "urlopen", request)
    with pytest.raises(RuntimeError, match="exited"):
        harness.wait_ready(Mock(poll=lambda: 1), "http://localhost:1")
    request.assert_not_called()


def test_readiness_has_a_whole_run_deadline(monkeypatch):
    monkeypatch.setattr(harness.urllib.request, "urlopen", Mock(side_effect=OSError))
    with pytest.raises(TimeoutError, match="deadline"):
        harness.wait_ready(Mock(poll=lambda: None), "http://localhost:1", timeout=.01)


def test_rendered_tick_geometry_detects_duplicate_labels_and_inverted_losses():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"]
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 800})
            page.set_content('''<svg width="300" height="200">
              <g class="recharts-xAxis-tick-labels">
                <text class="recharts-cartesian-axis-tick-value" x="20" y="100">1 Jan</text>
                <text class="recharts-cartesian-axis-tick-value" x="20" y="100">1 Jan</text>
              </g><g class="recharts-yAxis-tick-labels">
                <text class="recharts-cartesian-axis-tick-value" x="20" y="50">-10%</text>
                <text class="recharts-cartesian-axis-tick-value" x="20" y="80">0%</text>
              </g></svg>''')
            failures = contracts.geometry_failures(contracts.measure_page(page))
            assert set(failures) == {"duplicate-date-labels", "overlapping-date-labels",
                                     "inverted-drawdown"}
            page.set_content('''<article class="surface-card" style="background:rgb(17,26,46)">
              <p style="color:rgb(226,232,240)">Readable metric</p></article>''')
            assert contracts.measure_page(page)["cardMinContrast"] > 10
            page.locator("p").evaluate("e => e.style.color = 'rgb(20,30,40)'")
            assert "metric-card-text-contrast" in contracts.geometry_failures(contracts.measure_page(page))
        finally:
            browser.close()


def test_long_name_fixture_preserves_values_identifiers_and_original_payload():
    fixtures = importlib.import_module("ui_fixtures")
    original = {"security_name": "Asset", "identifier": "ABC", "account_name": "ISA",
                "value_gbp": 100, "by_account": {"ISA": 100}}
    transformed = fixtures.long_names(original)
    assert len(transformed["security_name"]) > 100
    assert transformed["identifier"] == "ABC"
    assert transformed["value_gbp"] == 100
    assert list(transformed["by_account"].values()) == [100]
    assert original["security_name"] == "Asset"


def test_geometry_rejects_known_defects_without_accepting_a_screenshot():
    failures = contracts.geometry_failures({
        "document": 943, "viewport": 390, "axes": [{"duplicates": 1, "overlaps": 1}],
        "invertedDrawdown": True, "clippedControls": ["Long tab"],
    })
    assert set(failures) == {"document-overflow", "duplicate-date-labels",
                             "overlapping-date-labels", "inverted-drawdown", "clipped-controls"}
