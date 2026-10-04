"""Assemble authorized catalog metadata from one authenticated snapshot."""

from pydantic import ValidationError

from trinity.auth.permissions import permitted_dataset_keys
from trinity.auth.schemas import Publication
from trinity.catalog.registry import describe_dataset, describe_metric
from trinity.catalog.schemas import CatalogResponse, Freshness, LastRefresh, utc_timestamp
from trinity.errors import Problem
from trinity.publication.repository import read_publication
from trinity.refresh.repository import read_last_refresh


def get_catalog(principal, connection) -> CatalogResponse:
    """Return permitted definitions and state using the authenticated connection.

    Authorize before protected reads. No publication still permits metadata;
    unreadable or inconsistent stored state returns a dependency failure.
    """
    datasets = [describe_dataset(key) for key in permitted_dataset_keys(principal)]
    metric = describe_metric()
    # Only persisted-value validation belongs to the dependency error boundary.
    try:
        publication = read_publication(connection)
        if publication is not None:
            publication = Publication(**publication.model_dump())
            if not publication.coverage_start <= publication.latest_observation_date <= publication.coverage_end:
                raise ValueError("Invalid publication coverage")
            publication = publication.model_copy(update={
                "published_at": utc_timestamp(publication.published_at),
            })
        row = read_last_refresh(connection)
        last_refresh = LastRefresh(**row) if row is not None else None
    except (ValidationError, ValueError, KeyError):
        raise Problem(503, "dependency_unavailable") from None
    return CatalogResponse(
        datasets=datasets, metrics=[metric], data_ready=publication is not None,
        publication=publication,
        freshness=Freshness(
            latest_observation_date=publication.latest_observation_date if publication else None,
            published_at=publication.published_at if publication else None,
            last_refresh=last_refresh,
        ),
    )
