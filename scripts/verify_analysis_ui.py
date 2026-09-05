"""Rehearse seven analytical routes against a read-only SQLite copy.

Requires the existing Playwright package and Chrome; no installs, migrations,
provider refresh, deployment, or normal application startup. Reports include
private screenshots: keep --output outside the repository. Any failed contract
exits nonzero *after* saving evidence; loading/empty/error pages cannot pass.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

from ui_contracts import ROUTES, allowed_gets, geometry_failures, measure_page, request_allowed
from ui_fixtures import EMPTY_SUMMARY, focus_controls, long_names, verify_accessibility
from ui_r3_contracts import verify_r3_navigation
from ui_scope_contracts import verify_episode_navigation, verify_scope_navigation, verify_timeline_navigation

REPO = Path(__file__).resolve().parents[1]


def create_app(database: Path, dist: Path):
    """Copy only audited GET routes, never the live application's lifespan."""
    sys.path.insert(0, str(REPO / "backend"))
    from fastapi import APIRouter, FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.database import get_session
    from app.main import app as original

    engine = create_async_engine(f"sqlite+aiosqlite:///{database.as_uri()}?mode=ro&uri=true")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def read_only_session():
        async with sessions() as session:
            yield session

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.dependency_overrides[get_session] = read_only_session

    @app.middleware("http")
    async def block_mutation(request, call_next):
        if request.method != "GET":
            return JSONResponse({"detail": "Read-only rehearsal"}, status_code=405)
        return await call_next(request)

    selected = APIRouter()
    for route in original.routes:
        if getattr(route, "path", "") in allowed_gets() and "GET" in getattr(route, "methods", set()):
            selected.routes.append(route)
    # include_router clones API routes with this app's dependency provider.
    # Appending original routes directly would retain the live DB dependency.
    app.include_router(selected)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(dist / "index.html")

    return app, engine


def serve(database: Path, dist: Path, port: int) -> None:
    import asyncio
    import uvicorn

    app, engine = create_app(database, dist)

    async def run():
        try:
            await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off")).serve()
        finally:
            await engine.dispose()

    asyncio.run(run())


def wait_ready(server, base: str, *, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("QA server exited; see server.log")
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=min(1, max(.01, deadline-time.monotonic()))) as response:
                if json.load(response).get("status") == "ok":
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    raise TimeoutError("QA server readiness deadline exceeded; see server.log")


def copy_database(database: Path, copy: Path) -> None:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(copy)) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("Copied SQLite database failed integrity check")


def verify_view(browser, base: str, view: str, width: int, output: Path, scenario: str = "default") -> dict:
    contract = dict(ROUTES[view])
    if scenario in {"empty", "error"}:
        contract["required"] = "/api/portfolio/summary"
        contract["heading"] = "Welcome to your portfolio"
    page = browser.new_page(viewport={"width": width, "height": 1000},
                            device_scale_factor=2 if width == 720 else 1, reduced_motion="reduce", has_touch=width <= 390)
    page.set_default_timeout(8000)
    errors, blocked, responses = [], [], []
    result = {"page": view, "width": width, "scenario": scenario, "errors": errors, "blocked": blocked, "requests": responses, "failures": []}
    page.on("pageerror", lambda error: errors.append(str(error)))

    def guard(route):
        request = route.request
        if request_allowed(request.method, request.url, base, view):
            if request.url.split("?")[0] == base + "/api/portfolio/summary" and scenario in {"empty", "error"}:
                route.fulfill(status=503 if scenario == "error" else 200,
                              json={"detail": "Synthetic fetch failure"} if scenario == "error" else EMPTY_SUMMARY)
            elif scenario == "empty" and request.url.split("?")[0] == base + "/api/instruments":
                route.fulfill(status=200, json=[])
            elif scenario == "long-names" and "/api/" in request.url:
                response = route.fetch()
                route.fulfill(response=response, json=long_names(response.json()))
            else:
                route.continue_()
        elif request.url.startswith("https://fonts.googleapis.com/") and request.method == "GET":
            # Deterministic offline system fonts, not an external network request.
            route.fulfill(status=200, content_type="text/css", body="")
        else:
            blocked.append({"method": request.method, "url": request.url})
            route.abort()

    def response_received(response):
        if "/api/" in response.url:
            responses.append({"url": response.url, "status": response.status})

    page.route("**/*", guard)
    page.on("response", response_received)
    try:
        with page.expect_response(lambda r: r.url.split("?")[0] == base + contract["required"]) as pending:
            page.goto(base + contract["url"], wait_until="networkidle", timeout=20000)
        response = pending.value
        if response.status != (503 if scenario == "error" else 200) or not response.json():
            raise AssertionError("Required analytics response failed or was empty")
        if view == "overview" and scenario not in {"empty", "error"}:
            payload = response.json()
            if not payload.get("growth_curve"):
                raise AssertionError("No snapshot fixture loaded")
            if payload.get("flow_adjusted", {}).get("total_return_pct") is None and payload.get("flow_adjusted_curve"):
                result["failures"].append("invalid-performance-publishes-curve")
            attribution = page.get_by_role("region", name="Snapshot change breakdown", exact=True)
            if attribution.locator("svg").count():
                result["failures"].append("removed-value-walk-returned")
        if scenario == "error":
            page.get_by_role("alert").filter(has_text="Unable to load portfolio summary").wait_for()
        else:
            page.get_by_role("heading", name=contract["heading"], exact=True).wait_for()
        measurement = measure_page(page)
        result["measurement"] = measurement
        result["failures"].extend(geometry_failures(measurement))
        if view == "overview":
            valid_curve = response.json().get("flow_adjusted_curve", [])
            if valid_curve and len(measurement["performanceDots"]) < len(valid_curve):
                result["failures"].append("missing-snapshot-observation-markers")
            if valid_curve and (not measurement["axes"] or any(not axis["ticks"] for axis in measurement["axes"])):
                result["failures"].append("missing-chart-axis-labels")
            if not valid_curve and measurement["performanceDots"]:
                result["failures"].append("unavailable-curve-plotted")
        if view == "overview" and scenario not in {"empty", "error"}:
            if width == 1440 and (measurement["primaryTop"] is None or measurement["primaryTop"] >= 1000):
                result["failures"].append("primary-performance-below-fold")
            if (width == 1440 and measurement["height"] > 2200) or (width <= 390 and measurement["height"] > 3600):
                result["failures"].append("dashboard-height-budget")
        if view == "performance":
            tabs = page.get_by_role("group", name="History chart views")
            if tabs.count():
                for label in ("Current-price reconstruction", "Capital deployment", "Snapshot history"):
                    button = tabs.get_by_role("button", name=label, exact=True)
                    button.focus()
                    button.press("Enter")
                    if button.get_attribute("aria-pressed") != "true":
                        result["failures"].append("unreachable-history-tab")
        if view == "allocation":
            for label in ("Account", "Source currency", "Sector", "Region", "Asset class"):
                page.get_by_role("button", name=label, exact=True).click()
                page.get_by_role("table", name="By " + label.lower(), exact=True).wait_for()
                page.get_by_role("button", name="Show exact values", exact=True).click()
                page.get_by_role("button", name="Show rounded values", exact=True).wait_for()
                colours = page.evaluate("""() => ({
                    slices:[...document.querySelectorAll('path.recharts-sector')].map(e=>getComputedStyle(e).fill),
                    swatches:[...document.querySelectorAll('table tbody th span')].map(e=>getComputedStyle(e).backgroundColor)
                })""")
                if not colours["slices"] or colours["slices"] != colours["swatches"]:
                    result["failures"].append("allocation-legend-colour-mismatch:" + label)
                result["failures"].extend(geometry_failures(measure_page(page)))
                page.get_by_role("button", name="Show rounded values", exact=True).click()
        if view == "performance" and scenario == "default" and width in (390, 1440):
            result["episode_navigation"] = verify_episode_navigation(page, response.json())
            result["timeline_navigation"] = verify_timeline_navigation(page, touch=width <= 390, output=output)
        if view == "overview" and scenario == "default" and width in (390, 1440):
            result["scope_navigation"] = verify_scope_navigation(page, width)
        result["accessibility"] = verify_accessibility(page, touch=width <= 390)
        focus = focus_controls(page)
        result["focus"] = focus
        if focus["failures"]:
            result["failures"].append("unreachable-focused-controls")
        if errors or blocked or any(r["status"] >= 400 and not (
            scenario == "error" and r["url"].endswith("/api/portfolio/summary") and r["status"] == 503
        ) for r in responses):
            result["failures"].append("browser-or-api-errors")
    except Exception as exc:
        result["failures"].append(f"readiness-or-contract: {exc}")
    finally:
        # The focus sweep leaves nested scrollers wherever the last control
        # sat; screenshots must show the resting state, not that residue.
        page.evaluate("""() => {
            document.activeElement?.blur();
            window.scrollTo(0, 0);
            for (const el of document.querySelectorAll('main *')) {
                if (el.scrollTop) el.scrollTop = 0;
                if (el.scrollLeft) el.scrollLeft = 0;
            }
        }""")
        page.mouse.move(0, 0)
        page.screenshot(path=str(output / f"{view}-{width}-{scenario}.png"), full_page=True)
        page.close()
    return result


def verify(database: Path, dist: Path, output: Path) -> None:
    from playwright.sync_api import sync_playwright

    if not database.is_file() or not (dist / "index.html").is_file():
        raise ValueError("An existing database and built frontend index.html are required")
    if output.is_relative_to(REPO) or dist.is_relative_to(REPO):
        raise ValueError("Rehearsal output and built UI must be outside the repository")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="stocks-ui-") as temporary:
        copy = Path(temporary) / "portfolio.db"
        copy_database(database, copy)
        copy_hash = hashlib.sha256(copy.read_bytes()).hexdigest()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        report = {"views": [], "journeys": [], "read_only_copy": True, "visual_inspection": "outstanding"}
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--database", str(copy),
                 "--dist", str(dist), "--serve", str(port)], stdout=log, stderr=subprocess.STDOUT,
                env={**os.environ, "PORTFOLIO_DATABASE_URL": "sqlite+aiosqlite:///:memory:"},
            )
            try:
                wait_ready(server, base)
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
                    try:
                        for width in (320, 390, 720, 768, 1440):
                            for view in ROUTES:
                                if server.poll() is not None:
                                    raise RuntimeError("QA server exited during browser checks")
                                for scenario in ("default", "long-names"):
                                    report["views"].append(verify_view(browser, base, view, width, output, scenario))
                            for scenario in ("empty", "error"):
                                report["views"].append(verify_view(browser, base, "overview", width, output, scenario))
                        for width in (390, 1440):
                            report["journeys"].append(verify_r3_navigation(browser, base, output, width))
                    finally:
                        browser.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                report["copy_unchanged"] = hashlib.sha256(copy.read_bytes()).hexdigest() == copy_hash
                (output / "report.json").write_text(json.dumps(report, indent=2))
        failures = sum(bool(view["failures"]) for view in report["views"])
        journey_failures = sum(len(j["failures"]) for j in report["journeys"])
        print(f"{len(report['views'])} route/width checks, {failures} failed; evidence: {output}")
        print(f"{sum(len(j['checks']) for j in report['journeys'])} navigation journeys; {journey_failures} failures")
        if failures or journey_failures or not report["copy_unchanged"]:
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/tmp/stocks-ui-verification"))
    parser.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(args.database.resolve(), args.dist.resolve(), args.serve)
    else:
        verify(args.database.resolve(), args.dist.resolve(), args.output.resolve())
