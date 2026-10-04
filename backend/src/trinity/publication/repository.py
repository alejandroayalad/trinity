"""Resolve the active publication from application state only."""
from dataclasses import dataclass
import re

from trinity.auth.schemas import Publication
from trinity.errors import Problem


def read_publication(connection):
    """Return null only for an existing empty pointer, never a failed join."""
    row = connection.execute("""
        SELECT a.publication_event_id, p.version_id, p.published_at,
               v.coverage_start, v.coverage_end, v.latest_observation_date,
               v.status, v.disposition, r.status AS run_status
        FROM active_publication a
        LEFT JOIN publication_events p ON p.id=a.publication_event_id
        LEFT JOIN data_versions v ON v.id=p.version_id
        LEFT JOIN refresh_runs r ON r.id=v.run_id WHERE a.id=1
        """).fetchone()
    if row is None:
        raise Problem(503, "dependency_unavailable")
    if row["publication_event_id"] is None:
        return None
    if (row["version_id"] is None or row["status"] != "validated"
            or row["disposition"] != "active" or row["run_status"] != "succeeded"):
        raise Problem(503, "dependency_unavailable")
    return Publication(**{k: row[k] for k in Publication.model_fields})


@dataclass(frozen=True)
class PinnedPublication:
    """Bind public metadata to a frozen internal manifest identity."""
    publication: Publication
    manifest_sha256: str
    contract_version: str


def read_pinned_publication(connection):
    """Read metadata and frozen file authority in the caller's one snapshot."""
    row = connection.execute("""
        SELECT a.publication_event_id,p.version_id,p.published_at,
               v.coverage_start,v.coverage_end,v.latest_observation_date,
               v.status,v.disposition,r.status AS run_status,
               v.manifest_sha256,v.manifest_frozen_at,v.contract_version
        FROM active_publication a
        LEFT JOIN publication_events p ON p.id=a.publication_event_id
        LEFT JOIN data_versions v ON v.id=p.version_id
        LEFT JOIN refresh_runs r ON r.id=v.run_id WHERE a.id=1
    """).fetchone()
    if row is None:
        raise Problem(503, "dependency_unavailable")
    if row["publication_event_id"] is None:
        return None
    if (row["version_id"] is None or row["status"] != "validated"
            or row["disposition"] != "active" or row["run_status"] != "succeeded"
            or row["manifest_frozen_at"] is None or row["contract_version"] != "trinity-data-v1"
            or re.fullmatch(r"[0-9a-f]{64}", row["manifest_sha256"] or "") is None):
        raise Problem(503, "dependency_unavailable")
    return PinnedPublication(Publication(**{k: row[k] for k in Publication.model_fields}),
                             row["manifest_sha256"], row["contract_version"])
