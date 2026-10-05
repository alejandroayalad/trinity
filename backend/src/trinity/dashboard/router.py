"""Expose bounded national reads with the same runtime activation gate as preview."""
from fastapi import APIRouter, Depends, Request
from trinity.auth.dependencies import bearer_token
from trinity.dashboard.service import NationalService
from trinity.queries.router import supervised_call

router = APIRouter(prefix='/api/v1', tags=['dashboard'])


def service(request, *, metric=False):
    """Build a lazy service; disabled execution still fails closed."""
    from trinity.queries.config import preview_execution_factory
    database = request.app.state.auth.database
    return NationalService(database, lambda: preview_execution_factory(
        database, enabled=request.app.state.preview_enabled), metric=metric)


@router.get('/dashboard/national')
async def dashboard(request: Request, token: str = Depends(bearer_token)):
    """Read a national range after current session authorization."""
    return await supervised_call(request, service(request).national, token,
                                 request.query_params.multi_items(), body=await request.body())


@router.get('/metrics/offline-share')
async def metric(request: Request, token: str = Depends(bearer_token)):
    """Read the exact same metric calculation for one requested calendar date."""
    return await supervised_call(request, service(request, metric=True).national, token,
                                 request.query_params.multi_items(), body=await request.body())
