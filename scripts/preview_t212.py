"""Loopback synthetic preview of the standalone Trading 212 button.

Only the exact fixture POST is simulated. All underlying portfolio routes use
an EXCLUSIVE synthetic database opened read-only. No worker, real credentials,
provider, systemd command, migration or production database is used. This is
UI acceptance, NOT a real service/security rehearsal.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class Trading212Fixture:
    def __init__(self, app):
        self.app = app
        self.request_id = None
        self.polls = 0

    async def __call__(self, scope, receive, send):
        from starlette.responses import JSONResponse

        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        headers = scope["headers"]
        origin = [value.decode() for name, value in headers if name == b"origin"]
        host = next((value.decode() for name, value in headers if name == b"host"), "")
        if method != "GET" and (path != "/api/sync/trading212/request" or method != "POST"):
            return await JSONResponse({"detail": "Synthetic read-only preview"}, status_code=405)(scope, receive, send)
        if path == "/api/sync/status":
            value = {"manual_sync_enabled": False, "service_trigger_enabled": True,
                     "accounts": [], "stale_after_days": 7, "last_run": None, "running": False,
                     "schedule": "SYNTHETIC preview only; no real scheduler"}
        elif path == "/api/trading212/status":
            value = {"configured": False, "account_name": "Trading 212"}
        elif path == "/api/sync/trading212/request":
            if method == "POST":
                if origin != ["http://" + host]:
                    return await JSONResponse({"detail": "Cross-origin preview request"}, status_code=403)(scope, receive, send)
                body = b""
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body += message.get("body", b"")
                    if body or not message.get("more_body"):
                        break
                if body or scope["query_string"]:
                    return await JSONResponse({"detail": "No parameters accepted"}, status_code=400)(scope, receive, send)
                self.request_id, self.polls = uuid.uuid4().hex, 0
                value = {"state": "accepted", "request_id": self.request_id}
            else:
                self.polls += 1
                finished = self.request_id is not None and self.polls >= 2
                stamp = dt.datetime.now(dt.UTC).isoformat()
                value = {"state": "completed" if finished else ("running" if self.request_id else "inactive"),
                         "request_id": self.request_id, "last_run": {
                             "schema_version": 2, "outcome": "complete", "ok": True,
                             "started_at": stamp, "finished_at": stamp, "freshness": {},
                             "steps": [{"name": "Trading 212", "status": "unchanged", "detail": None, "sections": {}}],
                             "files": [],
                         } if finished else None}
        else:
            return await self.app(scope, receive, send)
        return await JSONResponse(value, status_code=202 if method == "POST" else 200)(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new disposable directory outside repo")
    parser.add_argument("--port", type=int, default=8128)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port")
    if any((REPO / name).exists() or (REPO / name).is_symlink() for name in (".env", "backend/.env")):
        parser.error("Private dotenv reads forbidden")
    output = args.output.resolve()
    if output.is_relative_to(REPO):
        parser.error("Fixture output must be outside repo")
    dist = REPO / "frontend/dist"
    if not (dist / "index.html").is_file():
        parser.error("Build frontend first")
    for key in tuple(os.environ):
        if key.startswith("PORTFOLIO_"):
            del os.environ[key]
    os.environ["PORTFOLIO_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["PORTFOLIO_DEPLOYMENT_MODE"] = "local"
    sys.path.insert(0, str(REPO / "backend"))
    from pydantic_settings import DotEnvSettingsSource
    DotEnvSettingsSource._read_env_files = lambda self: {}
    DotEnvSettingsSource.__call__ = lambda self: {}
    from synthetic_preview import create_synthetic_database
    from verify_analysis_ui import create_app
    import uvicorn
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    database = output / "synthetic.db"
    asyncio.run(create_synthetic_database(database))
    app, engine = create_app(database, dist)
    print(f"SYNTHETIC ONLY preview: http://127.0.0.1:{args.port}/data", flush=True)

    async def serve():
        try:
            await uvicorn.Server(uvicorn.Config(Trading212Fixture(app), host="127.0.0.1", port=args.port, lifespan="off")).serve()
        finally:
            await engine.dispose()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
