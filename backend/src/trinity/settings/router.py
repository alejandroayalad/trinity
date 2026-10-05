"""Expose Admin settings reads, revision-checked writes and schedule status."""
from fastapi import APIRouter, Depends, Request, Response
from trinity.auth.dependencies import require_capability
from trinity.settings.schemas import SettingsResponse
from trinity.settings.service import get_settings

router = APIRouter(prefix="/api/v1")


@router.get("/settings", response_model=SettingsResponse)
def settings(response: Response, context=Depends(require_capability("settings:read"))):
    """Read shared settings only for an authorized Admin."""
    result = get_settings(*context)
    response.headers["ETag"] = f'"settings-{result.revision}"'
    return result


@router.put('/settings', response_model=SettingsResponse)
async def save_settings(request: Request, response: Response):
    """Save only after a current Admin and exact settings revision are verified."""
    import asyncio
    from trinity.auth.dependencies import bearer_token
    from trinity.settings.commands import SettingsService
    token = bearer_token(request)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        from trinity.errors import Problem
        raise Problem(415, 'unsupported_media_type')
    result = await asyncio.to_thread(SettingsService(request.app.state.auth.database).save,
        token, await request.body(), request.headers.getlist('if-match'), request.query_params.multi_items())
    response.headers['ETag'] = f'"settings-{result.revision}"'
    return result


@router.get('/settings/schedule-status')
async def schedule_status(request: Request):
    """Expose the next eligible wall-clock occurrence, not a dispatch promise."""
    import asyncio
    from trinity.auth.dependencies import bearer_token
    from trinity.settings.commands import SettingsService
    return await asyncio.to_thread(SettingsService(request.app.state.auth.database).status,
        bearer_token(request), request.query_params.multi_items(), body=await request.body())
