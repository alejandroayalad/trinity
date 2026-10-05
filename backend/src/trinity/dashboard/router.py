"""Expose national responses through the shared disconnect-aware supervisor."""

from fastapi import APIRouter, Depends, Request

from trinity.auth.dependencies import bearer_token
from trinity.dashboard.schemas import DashboardResponse, MetricResponse
from trinity.dashboard.service import NationalService
from trinity.queries.router import supervised_call

router = APIRouter(prefix='/api/v1', tags=['dashboard'])


def _service(request):
    """Construct lazy execution only when no controlled service was injected."""
    service = request.app.state.national_service
    if service is None:
        from trinity.queries.config import preview_execution_factory
        database = request.app.state.auth.database
        service = NationalService(database, lambda: preview_execution_factory(
            database, enabled=request.app.state.preview_enabled,
        ))
    return service


@router.get('/dashboard/national', response_model=DashboardResponse)
async def national_dashboard(request: Request, token: str = Depends(bearer_token)):
    """Keep duplicate pairs and the body for identity-first strict validation."""
    return await supervised_call(request, _service(request).dashboard, token,
                                 request.query_params.multi_items(), body=await request.body())


@router.get('/metrics/offline-share', response_model=MetricResponse)
async def national_metric(request: Request, token: str = Depends(bearer_token)):
    """Use the same supervision and session boundary for a single-date metric."""
    return await supervised_call(request, _service(request).metric, token,
                                 request.query_params.multi_items(), body=await request.body())
