"""Exercise the real HTTPS proxy/app/browser on disposable data, loopback only.

Requires built frontend, Playwright and an existing Caddy binary. Never installs
certificates/services or touches the normal portfolio. Evidence is synthetic.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.security import hash_password


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main() -> None:
    import httpx
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert (args.dist / "index.html").is_file(), "Build frontend before rehearsal"
    assert args.caddy.is_file(), "Provide an existing Caddy binary"
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = args.output.resolve()
    backend_port, tls_port = free_port(), free_port()
    origin = f"https://localhost:{tls_port}"
    password = secrets.token_urlsafe(32)
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT / "backend"),
            "PORTFOLIO_DEPLOYMENT_MODE": "public",
            "PORTFOLIO_PUBLIC_ORIGIN": origin,
            "PORTFOLIO_AUTH_USERNAME": "rehearsal",
            "PORTFOLIO_AUTH_PASSWORD_HASH": hash_password(password),
            "PORTFOLIO_DATABASE_URL": f"sqlite+aiosqlite:///{output / 'disposable.db'}",
            "PORTFOLIO_FRONTEND_DIST": str(args.dist.resolve()),
            "PORTFOLIO_TRADING212_API_KEY": "",
            "PORTFOLIO_TRADING212_API_SECRET": "",
            "XDG_DATA_HOME": str(output / "caddy-data"),
            "XDG_CONFIG_HOME": str(output / "caddy-config"),
            "STOCKS_ORIGIN": origin,
        }
    )
    config = (ROOT / "deploy/Caddyfile").read_text()
    config = config.replace(
        "{\n    servers",
        "{\n    admin off\n    auto_https disable_redirects\n    skip_install_trust\n    servers",
        1,
    )
    config = config.replace(
        "{$STOCKS_ORIGIN} {",
        "{$STOCKS_ORIGIN} {\n    bind 127.0.0.1\n    tls internal",
        1,
    )
    config = config.replace("127.0.0.1:8000", f"127.0.0.1:{backend_port}")
    config_path = output / "Caddyfile"
    config_path.write_text(config)
    processes = []
    report = {"data": "synthetic empty database", "origin": origin, "checks": []}
    logs = ExitStack()
    try:
        for name, command in [
            (
                "app",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                    "--workers",
                    "1",
                    "--proxy-headers",
                    "--forwarded-allow-ips",
                    "127.0.0.1",
                    "--no-access-log",
                    "--no-server-header",
                ],
            ),
            (
                "caddy",
                [
                    str(args.caddy.resolve()),
                    "run",
                    "--config",
                    str(config_path),
                    "--adapter",
                    "caddyfile",
                ],
            ),
        ]:
            log = logs.enter_context(open(output / f"{name}.log", "w"))  # noqa: SIM115 - ExitStack closes in finally.
            processes.append(
                subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
            )
        deadline = time.monotonic() + 40
        with httpx.Client(verify=False, trust_env=False, timeout=2) as readiness:
            while True:
                assert all(p.poll() is None for p in processes), (
                    "Child exited; inspect private rehearsal logs"
                )
                try:
                    ready = readiness.get(origin + "/api/health").status_code == 401
                except httpx.HTTPError:
                    ready = False
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("HTTPS rehearsal readiness timeout")
                time.sleep(0.2)
        roots = list((output / "caddy-data").rglob("root.crt"))
        assert len(roots) == 1, "Expected one private test CA"
        # API acceptance checks validate the generated test certificate properly.
        tls = ssl.create_default_context(cafile=str(roots[0]))
        with httpx.Client(verify=tls, trust_env=False, timeout=30) as client:
            for path in ["/", "/portfolio", "/api/health", "/api/groups"]:
                assert client.get(origin + path).status_code == 401, path
            assert (
                client.post(
                    origin + "/api/groups", json={"name": "unauthorized"}
                ).status_code
                == 401
            )
            report["checks"].append("unauthenticated UI/API reads and writes denied")
            client.auth = ("rehearsal", password)
            assert client.get(origin + "/api/health").status_code == 200
            assert (
                client.get(
                    origin + "/portfolio?tab=holdings", headers={"Accept": "text/html"}
                ).status_code
                == 200
            )
            assert client.get(origin + "/api/does-not-exist").status_code == 404
            assert client.get(origin + "/assets/does-not-exist.js").status_code == 404
            for headers in [{}, {"Origin": "https://evil.example"}]:
                assert (
                    client.post(
                        origin + "/api/groups",
                        json={"name": "blocked"},
                        headers=headers,
                    ).status_code
                    == 403
                )
            report["checks"].append(
                "TLS verified; authenticated reads, deep links, API/asset 404 and CSRF checks passed"
            )
            response = client.get(origin + "/api/health")
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert "strict-transport-security" not in response.headers
            report["checks"].append(
                "privacy/security headers and no shared-host HSTS verified"
            )
        with sync_playwright() as playwright:
            chrome = shutil.which("google-chrome") or shutil.which("chromium")
            assert chrome, "Install/configure a browser separately before rehearsal"
            browser = playwright.chromium.launch(executable_path=chrome, headless=True)
            # Private test CA is not installed into OS/browser trust; this exception
            # applies only to the loopback rehearsal, not public certificate checks.
            context = browser.new_context(
                http_credentials={"username": "rehearsal", "password": password},
                ignore_https_errors=True,
                viewport={"width": 1440, "height": 1000},
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(origin + "/")
                    else route.abort()
                ),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.goto(origin + "/portfolio?tab=groups", wait_until="networkidle")
            page.locator("main").wait_for()
            assert "Groups" in page.locator("body").inner_text()
            result = page.evaluate("""async () => {
                const made = await fetch('/api/groups', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:'HTTPS rehearsal group'})});
                const item = await made.json();
                const read = await fetch('/api/groups');
                const groups = await read.json();
                const exists = groups.some(g => g.id === item.id && g.name === 'HTTPS rehearsal group');
                const removed = await fetch('/api/groups/' + item.id, {method:'DELETE'});
                const after = await (await fetch('/api/groups')).json();
                return {created:made.status, exists, removed:removed.status, absent:!after.some(g => g.id === item.id)};
            }""")
            assert result == {
                "created": 201,
                "exists": True,
                "removed": 204,
                "absent": True,
            }, result
            report["checks"].append(
                "real browser same-origin create/read/delete persisted and read back on disposable DB"
            )
            page.screenshot(path=str(output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(origin + "/portfolio?tab=holdings", wait_until="networkidle")
            page.screenshot(path=str(output / "mobile.png"), full_page=True)
            assert not errors, errors
            report["checks"].append(
                "desktop/mobile frontend rendered without browser errors"
            )
            browser.close()
        report["result"] = "passed"
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        logs.close()
        report["children_stopped"] = all(p.poll() is not None for p in processes)
        (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
