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


class HealthResponse(BaseModel):
    """Process liveness only; does not report data or service readiness."""
    status: Literal["ok"] = "ok"


def create_app(*, settings=None, service=None) -> FastAPI:
    """Create the API; explicit dependency injection is reserved for tests."""
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
    application.include_router(catalog_router)

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return application


app = create_app()
