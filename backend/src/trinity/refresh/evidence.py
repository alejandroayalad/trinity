"""Load a saved preparation result without inventing replacement identities.

The trusted worker supplies its retained receipt hash and reserved candidate
root. Reconstruct typed validation/storage reports from the saved bytes, then
reuse the existing verifiers, including remote readback. No database writes
or publication authority belong here. Invalid evidence raises a safe error.
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import time
from uuid import UUID

from trinity.adapters.s3 import StoredArtifact, StorageError
from trinity.connector import parquet
from trinity.connector.pipeline import StoredCandidate, _read_storage_file, verify_stored_candidate
from trinity.connector.prepare import _verify_receipt
from trinity.connector.validate import CheckResult, ValidationReport
from trinity.contracts.manifest import canonical_json, read_json, read_manifest, sha256
from trinity.errors import Problem


class EvidenceError(Problem):
    """Retain a safe internal cause while preserving Refresh's public error."""

    def __init__(self, cause):
        super().__init__(503, "dependency_unavailable")
        self.cause = cause


@dataclass(frozen=True)
class CandidateEvidence:
    """Keep verified report identities; the database still checks ownership."""
    report: ValidationReport
    receipt: StoredCandidate
    preparation_receipt_sha256: str


def _results(items):
    """Reconstruct exact details and reject surplus or missing result fields."""
    fields = set(CheckResult.__dataclass_fields__) - {'details_json'}
    results = []
    for item in items:
        if set(item) != fields | {'details', 'details_sha256'}:
            raise ValueError
        details = canonical_json(item['details'])
        if sha256(details) != item['details_sha256']:
            raise ValueError
        results.append(CheckResult(**{key: item[key] for key in fields}, details_json=details))
    return tuple(results)


def load_candidate(root: Path, expected_receipt_sha256: str, storage, *, timeout_seconds=300):
    """Require parent completion, retained hashes and intact local/remote bytes.

    The expected hash must come from durable worker custody, not from a fresh
    hash of the file being checked. A child-only receipt cannot pass this gate.
    Remote verification uses the caller's bounded storage operation. Preserve
    all files on rejection; never repair or overwrite a candidate here.
    """
    verification_deadline = time.monotonic() + timeout_seconds
    try:
        if re.fullmatch('[0-9a-f]{64}', expected_receipt_sha256) is None:
            raise ValueError
        with parquet._directory(root) as descriptor:
            raw = _read_storage_file(descriptor, 'evidence/preparation/result.json')
            if sha256(raw) != expected_receipt_sha256:
                raise ValueError
            result = read_json(raw)
            start, end = (date.fromisoformat(result[key]) for key in ('requested_start', 'requested_end'))
            if _verify_receipt(root, expected_receipt_sha256, start, end) != result:
                raise ValueError
            # Parent completion is authoritative only when it has no retained
            # failure alongside it. The remote bundle excludes these journals.
            if 'evidence/preparation/failure.json' in parquet._inventory(descriptor):
                raise ValueError
            manifest = read_manifest(_read_storage_file(descriptor, 'manifest.json'), result['manifest_sha256'])
            attempt = result['attempt_id']
            if str(UUID(attempt)) != attempt:
                raise ValueError
            prefix = f'evidence/{attempt}'
            validation_raw = _read_storage_file(descriptor, f'{prefix}/validation.json')
            diagnostics_raw = _read_storage_file(descriptor, f'{prefix}/diagnostics.json')
            validation, diagnostics = read_json(validation_raw), read_json(diagnostics_raw)
            bundle = read_json(_read_storage_file(descriptor, 'bundle.json'))
            report = ValidationReport(root, manifest, attempt, _results(validation['results']),
                _results(diagnostics['evaluations']), validation['status'], result['warning_digest'],
                result['warning_count'], result['approval_required'], sha256(validation_raw), sha256(diagnostics_raw))
            receipt = StoredCandidate(root, manifest.version_id, attempt, manifest.digest,
                result['bundle_sha256'], tuple(StoredArtifact(**item) for item in bundle['artifacts']),
                result['storage_evidence_path'], result['warning_digest'], result['warning_count'],
                result['approval_required'])
        # Existing verification binds the summary hashes to the bundle and
        # checks every member. Hashing the summaries above does not trust them.
        verify_stored_candidate(report, receipt, storage, timeout_seconds=verification_deadline-time.monotonic())
        return CandidateEvidence(report, receipt, expected_receipt_sha256)
    except StorageError as error:
        # Only positively identified operational causes permit a later retry.
        cause = error.cause
        if cause not in ('storage_temporary', 'storage_deadline', 'storage_denied',
                         'storage_configuration', 'evidence_missing', 'unknown_failure'):
            cause = 'evidence_invalid' if cause in (
                'object_identity', 'unsafe_local_file', 'local_inventory_changed',
                'local_artifact_changed', 'local_identity', 'receipt_identity',
                'storage_incomplete', 'bundle_identity', 'reservation_identity',
                'plan_identity', 'bundle_inventory', 'snapshot_validation_identity',
                'stored_candidate_invalid', 'object_too_large') else 'unknown_failure'
        raise EvidenceError(cause) from None
    except FileNotFoundError:
        raise EvidenceError('evidence_missing') from None
    except (ValueError, TypeError, KeyError):
        raise EvidenceError('evidence_invalid') from None
    except Exception:
        raise EvidenceError('unknown_failure') from None
