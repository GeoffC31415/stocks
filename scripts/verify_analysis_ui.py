"""Rehearse analysis pages with an isolated read-only database and built UI.

Run from the repo root:
  .venv/bin/python scripts/verify_analysis_ui.py --database portfolio.db \
      --dist /tmp/stocks-final-dist --output /tmp/stocks-ui-check

Requires the existing Playwright Python package and Google Chrome. Never runs
application lifespan/migrations, modifies the supplied database, or deploys.
"""
from __future__ import annotations

import argparse
from contextlib import closing
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

REPO = Path(__file__).resolve().parents[1]


def serve(database: Path, dist: Path, port: int) -> None:
    os.environ["PORTFOLIO_DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database.as_uri()}?mode=ro&uri=true"
    )
    sys.path.insert(0, str(REPO / "backend"))
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from app.main import app as original

    app = FastAPI()
    allowed = {
        "/api/health", "/api/portfolio/allocation", "/api/portfolio/summary",
        "/api/portfolio/returns", "/api/portfolio/timeseries", "/api/portfolio/attribution",
        "/api/portfolio/performance", "/api/portfolio/benchmarks", "/api/instruments",
        "/api/orders/analytics", "/api/orders/cashflow-timeseries", "/api/orders/estimated-timeseries",
    }
    for route in original.routes:
        if getattr(route, "path", "") in allowed and "GET" in getattr(route, "methods", set()):
            app.router.routes.append(route)
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(dist / "index.html")

    uvicorn.run(app, host="127.0.0.1", port=port, lifespan="off")


def verify(database: Path, dist: Path, output: Path) -> None:
    from playwright.sync_api import sync_playwright

    if not database.is_file() or not (dist / "index.html").is_file():
        raise ValueError("An existing database and built frontend index.html are required")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stocks-ui-") as temporary:
        copy = Path(temporary) / "portfolio.db"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copy)) as destination:
                source.backup(destination)
                assert destination.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--database", str(copy),
                 "--dist", str(dist), "--serve", str(port)], stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 10
                while True:
                    if server.poll() is not None:
                        raise RuntimeError("QA server exited; see server.log")
                    try:
                        with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                            assert json.load(response)["status"] == "ok"
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                report = {"views": [], "source_database": str(database), "read_only_copy": True}
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
                    try:
                        for width in (390, 1440):
                            page = browser.new_page(viewport={"width": width, "height": 1000})
                            errors: list[str] = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.goto(base + "/portfolio?tab=allocation", wait_until="networkidle")
                            page.get_by_role("heading", name="Allocation & concentration").wait_for()
                            page.get_by_text("Invested value", exact=True).wait_for()
                            page.get_by_role("button", name="Refresh data", exact=True).wait_for(timeout=3000)
                            for label in ("Account", "Source currency", "Asset class"):
                                button = page.get_by_role("button", name=label, exact=True)
                                button.focus()
                                button.press("Enter")
                                page.wait_for_load_state("networkidle")
                                page.get_by_text("Invested value", exact=True).wait_for()
                                assert page.get_by_role("button", name=label, exact=True).get_attribute("aria-pressed") == "true"
                            size = page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
                            assert size["document"] <= size["viewport"], size
                            assert not errors, errors
                            page.screenshot(path=str(output / f"allocation-{width}.png"), full_page=True)
                            report["views"].append({"page": "allocation", "width": width, "size": size, "errors": list(errors)})
                            page.goto(base + "/", wait_until="networkidle")
                            page.get_by_role("heading", name="Performance", exact=True).wait_for()
                            attribution = page.get_by_role("region", name="Attribution waterfall", exact=True)
                            assert attribution.locator("svg").count() == 0
                            assert attribution.locator('[data-testid="waterfall-step"]').count() == 6
                            size = page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
                            if size["document"] > size["viewport"]:
                                print(json.dumps(page.evaluate("[...document.querySelectorAll('main *')].map(e=>({tag:e.tagName,cls:e.getAttribute('class'),text:e.innerText?.slice(0,80),right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(e=>e.right>innerWidth).slice(0,25)"), indent=2))
                            assert size["document"] <= size["viewport"], size
                            assert not errors, errors
                            page.screenshot(path=str(output / f"overview-{width}.png"), full_page=True)
                            report["views"].append({"page": "overview", "width": width, "size": size, "errors": list(errors)})
                            page.close()
                    finally:
                        browser.close()
                (output / "report.json").write_text(json.dumps(report, indent=2))
                print(json.dumps(report, indent=2))
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


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
