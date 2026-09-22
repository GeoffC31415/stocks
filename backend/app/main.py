from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException

from app import database
from app.config import Settings, settings
from app.database import init_db
from app.routers.cgt import router as cgt_router
from app.routers.groups import router as groups_router
from app.routers.imports import router as imports_router
from app.routers.instruments import router as instruments_router
from app.routers.market_data import router as market_data_router
from app.routers.matching import router as matching_router
from app.routers.orders import router as orders_router
from app.routers.portfolio import router as portfolio_router
from app.routers.trading212 import router as trading212_router
from app.security import WebSecurityMiddleware, validate_public_settings


class SPAStaticFiles(StaticFiles):
    """Serve assets normally; only extensionless HTML navigations get the SPA."""

    async def __call__(self, scope, receive, send):
        path = scope["path"]
        parts = path.strip("/").split("/")
        # Validate before StaticFiles normalizes dot segments. No hidden files,
        # double-encoding, Windows separators, or reserved API/docs namespaces.
        if (
            any(part.startswith(".") for part in parts)
            or any(char in path for char in ("\\", "%"))
            or any(ord(char) < 32 for char in path)
            or parts[0] in {"api", "docs", "redoc", "openapi.json"}
        ):
            raise HTTPException(status_code=404)
        await super().__call__(scope, receive, send)

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
        except HTTPException as error:
            if error.status_code != 404:
                raise
        parts = path.split("/")
        if (
            scope["method"] in {"GET", "HEAD"}
            and parts[0] != "assets"
            and not any("." in part for part in parts)
            and "text/html" in Headers(scope=scope).get("accept", "")
        ):
            return await super().get_response("index.html", scope)
        raise HTTPException(status_code=404)


class SecuredFastAPI(FastAPI):
    def build_middleware_stack(self):
        # Outside Starlette's ServerErrorMiddleware: errors and mounts must pass
        # through the same ASGI boundary as successful API responses.
        return WebSecurityMiddleware(super().build_middleware_stack(), self.state.web_config)


def create_app(config: Settings | None = None) -> FastAPI:
    """Build a web app using the database configured before module import.

    Web settings may vary per app, but the engine, sessions and migrations are
    process-global. Reject a different database rather than silently ignoring it.
    """
    config = config if config is not None else settings
    requested_url = make_url(config.resolved_database_url())
    session_bind = database.SessionLocal.kw.get("bind")
    if (
        requested_url != database.engine.url
        or session_bind is None
        or requested_url != session_bind.url
        or requested_url != make_url(database.settings.resolved_database_url())
    ):
        raise ValueError(
            "create_app database configuration must match the process database; "
            "set PORTFOLIO_DATABASE_URL before importing app.main"
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        validate_public_settings(config)
        await init_db()
        yield

    public = config.deployment_mode == "public"
    application = SecuredFastAPI(
        title="Portfolio Tracker API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if public else "/docs",
        redoc_url=None if public else "/redoc",
        openapi_url=None if public else "/openapi.json",
    )
    application.state.web_config = config
    if config.deployment_mode == "local":
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for router in (
        cgt_router,
        imports_router,
        orders_router,
        portfolio_router,
        instruments_router,
        groups_router,
        matching_router,
        market_data_router,
        trading212_router,
    ):
        application.include_router(router)

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if config.frontend_dist.exists():
        application.mount(
            "/", SPAStaticFiles(directory=config.frontend_dist, html=True), name="frontend"
        )
    return application


app = create_app()
