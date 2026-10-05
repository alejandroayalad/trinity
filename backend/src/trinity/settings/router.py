"""Expose the shared-settings read, save and schedule-status operations.

The PUT adapter passes raw bounded input to the service. The service checks
the session before it parses the precondition or body. No route starts a
refresh; the scheduler worker owns scheduled admission.
"""
from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool
from trinity.auth.dependencies import bearer_token, require_capability
from trinity.settings.schemas import ScheduleStatus, SettingsRequest, SettingsResponse
from trinity.settings.service import SettingsService, get_settings, schedule_status

router = APIRouter(prefix="/api/v1")


def service(request):
    """Use an injected service or the API-owned lazy database pool."""
    supplied = getattr(request.app.state, "settings_service", None)
    return supplied if supplied is not None else SettingsService(request.app.state.auth.database)


@router.get("/settings", response_model=SettingsResponse)
def settings(response: Response, context=Depends(require_capability("settings:read"))):
    """Read shared settings only for an authorized Admin."""
    result = get_settings(*context)
    response.headers["ETag"] = f'"settings-{result.revision}"'
    return result


@router.put("/settings", response_model=SettingsResponse, openapi_extra={
    "requestBody": {"required": True, "content": {"application/json": {"schema": SettingsRequest.model_json_schema()}}},
    "parameters": [{"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string"}}],
})
async def update_settings(request: Request, response: Response):
    """Save the schedule with a revision check; return the committed settings."""
    token = bearer_token(request)
    raw = await request.body()
    result = await run_in_threadpool(service(request).update, token, raw,
                                     request.headers.getlist("if-match"), request.query_params.multi_items())
    response.headers["ETag"] = f'"settings-{result.revision}"'
    return result


@router.get("/settings/schedule-status", response_model=ScheduleStatus)
def status(context=Depends(require_capability("settings:read"))):
    """Describe the next daily check and the current blocker without writing."""
    return schedule_status(*context)
