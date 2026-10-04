"""Expose the implemented read-only shared-settings operation."""
from fastapi import APIRouter, Depends, Response
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
