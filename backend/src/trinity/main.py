"""Create the authenticated local API without importing live infrastructure state.

Startup reads API configuration and opens a lazy database pool. Product requests
fail closed if PostgreSQL is unavailable; health reports process liveness only.
"""
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from trinity.adapters.postgres import Database
from trinity.auth.router import router
from trinity.auth.service import AuthService
from trinity.catalog.router import router as catalog_router
from trinity.config import load_api_settings
from trinity.errors import SafeTransport, install_handlers
from trinity.settings.router import router as settings_router
from trinity.queries.router import router as queries_router
from trinity.refresh.router import router as refresh_router
from trinity.refresh.candidates import router as candidates_router


class HealthResponse(BaseModel):
    """Process liveness only; does not report data or service readiness."""
    status: Literal["ok"] = "ok"


def create_app(*, settings=None, service=None, query_service=None, preview_service=None, refresh_service=None, enable_preview=False) -> FastAPI:
    """Return the API with auth, catalog, SQL and a delivery-gated preview route.

    Register startup and shutdown hooks without opening a database here.
    Startup loads the supplied or environment settings and opens the database pool.
    Tests can supply an authentication service to skip database initialization.
    Close the pool on shutdown or if authentication service creation fails.
    Health reports process liveness only; it does not prove data readiness.
    """
    @asynccontextmanager
    async def lifespan(application):
        database = None
        if service is None:
            database = Database(settings or load_api_settings())
            database.open()
            try:
                application.state.auth = AuthService(database)
            except Exception:
                database.close()
                raise
        else:
            application.state.auth = service
        application.state.query_service = query_service
        application.state.preview_service = preview_service
        application.state.refresh_service = refresh_service
        application.state.preview_enabled = enable_preview
        try:
            yield
        finally:
            if database:
                database.close()

    application = FastAPI(title="Trinity", version="0.1.0", lifespan=lifespan)
    application.add_middleware(SafeTransport)
    install_handlers(application)
    application.include_router(router)
    application.include_router(settings_router)
    application.include_router(queries_router)
    application.include_router(catalog_router)
    application.include_router(refresh_router)
    application.include_router(candidates_router)

    # The decorator registers this handler; the response model fixes the JSON shape.
    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Report process liveness without checking data or external services."""
        return HealthResponse()

    return application


# Uvicorn imports this object through "trinity.main:app"; startup needs no EIA key.
app = create_app()
