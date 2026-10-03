"""HTTP entrypoint for the minimum backend scaffold."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Process liveness only; does not report data or service readiness."""

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Create the API without opening external connections."""
    application = FastAPI(title="Trinity", version="0.1.0")

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return application


app = create_app()
