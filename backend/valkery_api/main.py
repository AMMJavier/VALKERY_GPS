"""Aplicación FastAPI.

Desarrollo (desde la carpeta backend):
    uvicorn valkery_api.main:app --reload --port 8000
Documentación interactiva: http://localhost:8000/docs

Referencia Traccar: api/ApiResourceConfig.java, web/WebServer.java
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.config import CoreSettings, get_core_settings
from valkery_core.db import create_engine, create_session_factory

from .api.v1 import router as v1_router
from .core.config import ApiSettings, get_api_settings
from .core.security import LoginGuard


def create_app(
    settings: ApiSettings | None = None,
    db_url: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    core_settings: CoreSettings | None = None,
) -> FastAPI:
    settings = settings or get_api_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        if session_factory is None:
            engine = create_engine(db_url)
            app.state.session_factory = create_session_factory(engine)
        else:
            app.state.session_factory = session_factory
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="VALKERY GPS API",
        version="0.4.0",
        lifespan=lifespan,
        description="Monitoreo del Teltonika FMC920. Autenticación: POST /api/v1/auth/login → Bearer token.",
    )
    app.state.settings = settings
    app.state.core_settings = core_settings or get_core_settings()
    if session_factory is not None:
        # Inyectada (pruebas): disponible aunque el cliente no ejecute el lifespan.
        app.state.session_factory = session_factory
    app.state.login_guard = LoginGuard(settings.login_max_attempts, settings.login_lockout_min * 60)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(v1_router)

    @app.get("/health", tags=["health"])
    async def health(request: Request) -> JSONResponse:
        try:
            async with request.app.state.session_factory() as db:
                await db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
        return JSONResponse({"status": "ok", "database": "ok"})

    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn valkery_api.main:app` crea la app al importarla (lee .env).
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
