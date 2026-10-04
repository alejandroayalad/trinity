"""HTTP entrypoint for the minimum backend scaffold."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Process liveness only; does not report data or service readiness."""

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Create the scaffold API without opening external connections.

    Register a liveness route and return the application for ASGI serving or tests.
    No credentials or application data are loaded. A successful health response
    proves only that this process can answer, not that external services are ready.
    """
    application = FastAPI(title="Trinity", version="0.1.0")

    # The decorator registers this handler; the response model fixes the JSON shape.
    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Report process liveness without checking data or external services."""
        return HealthResponse()

    return application


# Uvicorn imports this object through "trinity.main:app"; startup needs no EIA key.
app = create_app()
