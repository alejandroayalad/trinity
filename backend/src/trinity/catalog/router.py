"""Expose role-filtered catalog metadata without analytical reads."""

from fastapi import APIRouter, Depends

from trinity.auth.dependencies import require_capability
from trinity.catalog.schemas import CatalogResponse
from trinity.catalog.service import get_catalog

router = APIRouter(prefix="/api/v1")


@router.get("/catalog", response_model=CatalogResponse)
def catalog(context=Depends(require_capability("catalog:read"))):
    """Return definitions and freshness for the current trusted role."""
    return get_catalog(*context)
