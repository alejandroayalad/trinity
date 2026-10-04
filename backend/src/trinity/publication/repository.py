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


@dataclass(frozen=True)
class PreviewPublication(PinnedPublication):
    """Pin the stored bundle and its successful validation attempt in one snapshot."""
    evidence_bundle_sha256: str
    validation_attempt_id: str
    validation_checkset: str
    review_warning_digest: str
    review_warning_count: int
    approval_required: bool


def read_preview_publication(connection, pinned):
    """Require complete frozen evidence authority for the already pinned version.

    Call within the same read-only snapshot as read_pinned_publication. A saved
    candidate receipt alone supplies no active-publication authority.
    """
    from uuid import UUID
    row = connection.execute("""
        SELECT v.evidence_bundle_sha256,v.validation_attempt_id,v.validation_checkset,
               v.review_warning_digest,v.review_warning_count,v.approval_required,
               v.diagnostics_frozen_at,v.validated_at,v.validation_step_id,
               s.run_id=v.run_id AS same_run,s.stage,s.status AS step_status,s.finished_at,
               p.publication_mode,p.approval_id,
               a.version_id AS approved_version,a.manifest_sha256 AS approved_manifest,
               a.validation_step_id AS approved_step,a.review_warning_digest AS approved_digest
        FROM data_versions v JOIN refresh_steps s ON s.id=v.validation_step_id
        JOIN publication_events p ON p.version_id=v.id
        LEFT JOIN approvals a ON a.id=p.approval_id
        WHERE v.id=%s AND p.id=%s
    """, (pinned.publication.version_id, pinned.publication.publication_event_id)).fetchone()
    try:
        if (row is None or row['same_run'] is not True or row['stage'] != 'validate'
                or row['step_status'] != 'succeeded' or row['finished_at'] is None
                or row['diagnostics_frozen_at'] is None or row['validated_at'] is None
                or row['validation_checkset'] != 'trinity-data-v1'
                or type(row['review_warning_count']) is not int or row['review_warning_count'] < 0
                or type(row['approval_required']) is not bool
                or row['approval_required'] != (row['review_warning_count'] > 0)):
            raise ValueError
        for field in ('evidence_bundle_sha256', 'review_warning_digest'):
            if re.fullmatch(r'[0-9a-f]{64}', row[field] or '') is None:
                raise ValueError
        attempt = str(row['validation_attempt_id'])
        if str(UUID(attempt)) != attempt:
            raise ValueError
        if row['approval_required']:
            if (row['publication_mode'] != 'approval' or row['approval_id'] is None
                    or row['approved_version'] != pinned.publication.version_id
                    or row['approved_manifest'] != pinned.manifest_sha256
                    or row['approved_step'] != row['validation_step_id']
                    or row['approved_digest'] != row['review_warning_digest']):
                raise ValueError
        elif row['publication_mode'] != 'automatic' or row['approval_id'] is not None:
            raise ValueError
        return PreviewPublication(pinned.publication, pinned.manifest_sha256, pinned.contract_version,
                                  row['evidence_bundle_sha256'], attempt, row['validation_checkset'],
                                  row['review_warning_digest'], row['review_warning_count'], row['approval_required'])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Problem(503, 'dependency_unavailable') from None
