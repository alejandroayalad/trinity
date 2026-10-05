"""Use frozen database evidence for both action reads and publication commands."""
from datetime import datetime

from trinity.connector.validate import CheckResult, required_checks_pass, diagnostic_identity, ValidationError
from trinity.contracts.manifest import canonical_json, sha256
from trinity.errors import Problem

RECOVERABLE = frozenset(('storage_temporary', 'storage_deadline', 'publication_interrupted',
                         'publication_dispatch_exhausted', 'publication_deadline'))


def recorded(connection, run, version, *, evidence=None, require_approval=True):
    """Reject incomplete or mixed proof; never perform remote I/O here.

    Reconstruct the connector's check values from immutable rows. Reuse its
    required-check and diagnostic rules instead of creating another registry.
    When a worker supplies verified evidence, compare every stored result and
    artifact to that same report before allowing the final transaction.
    """
    if not version:
        raise Problem(409, 'candidate_ineligible')
    step = connection.execute('SELECT * FROM refresh_steps WHERE id=%s',
                              (version['validation_step_id'],)).fetchone()
    approval = connection.execute('SELECT * FROM approvals WHERE version_id=%s',
                                  (version['id'],)).fetchone()
    try:
        ref = run['worker_execution_ref'] or {}
        if (ref.get('version_id') != str(version['id'])
                or ref.get('receipt_sha256') != version['preparation_receipt_sha256']
                or version['status'] != 'validated' or version['disposition'] != 'active'
                or not version['preparation_receipt_sha256'] or not version['storage_verified_at']
                or not version['evidence_bundle_sha256'] or not version['diagnostics_frozen_at']
                or version['contract_version'] != 'trinity-data-v1'
                or version['validation_checkset'] != 'trinity-data-v1'
                or not step or step['run_id'] != run['id'] or step['stage'] != 'validate'
                or step['status'] != 'succeeded' or not step['finished_at']
                or step['validation_attempt_id'] != version['validation_attempt_id']
                or not step['validation_sha256'] or not step['diagnostics_sha256']):
            raise ValueError
        rows = connection.execute('SELECT * FROM validation_results WHERE version_id=%s AND step_id=%s',
                                  (version['id'], step['id'])).fetchall()
        results = []
        for row in rows:
            details = canonical_json(row['details'])
            if (sha256(details) != row['details_sha256']
                    or row['manifest_sha256'] != version['manifest_sha256']
                    or row['checkset_version'] != version['validation_checkset']
                    or row['details_path'] != f"evidence/{version['validation_attempt_id']}/{row['check_code']}-{row['dataset_key']}.json"):
                raise ValueError
            results.append(CheckResult(version_id=str(version['id']),
                attempt_id=str(version['validation_attempt_id']),
                **{key: row[key] for key in ('manifest_sha256','checkset_version','check_revision',
                    'dataset_key','required','severity','status','checked_count','failed_count','details_path')},
                check_code=row['check_code'], details_json=details,
                checked_at=row['checked_at'].isoformat().replace('+00:00','Z')))
        required = tuple(item for item in results if item.required)
        diagnostics = tuple(item for item in results if not item.required)
        if not required_checks_pass(required, version_id=str(version['id']),
                attempt_id=str(version['validation_attempt_id']), manifest_sha256=version['manifest_sha256']):
            raise ValueError
        digest, count, _ = diagnostic_identity(diagnostics)
        if (digest != version['review_warning_digest'] or count != version['review_warning_count']
                or version['approval_required'] != (count > 0)):
            raise ValueError
        artifacts = connection.execute('SELECT * FROM dataset_artifacts WHERE version_id=%s',
                                       (version['id'],)).fetchall()
        if {item['dataset_key'] for item in artifacts} != {'national','facility','generator'}:
            raise ValueError
        if (version['coverage_start'] != run['requested_start']
                or version['coverage_end'] != run['requested_end'] or not run['window_frozen_at']):
            raise ValueError
        if require_approval and version['approval_required']:
            if not approval or any(approval[k] != version[v] for k,v in (
                    ('version_id','id'), ('manifest_sha256','manifest_sha256'),
                    ('validation_step_id','validation_step_id'), ('review_warning_digest','review_warning_digest'))):
                raise ValueError
        if not version['approval_required'] and approval:
            raise ValueError
        if evidence is not None:
            from trinity.refresh.registration import _binding
            _binding(run, version, step, evidence)
            report = evidence.report
            if (evidence.preparation_receipt_sha256 != version['preparation_receipt_sha256']
                    or evidence.receipt.bundle_sha256 != version['evidence_bundle_sha256']
                    or report.validation_sha256 != step['validation_sha256']
                    or report.diagnostics_sha256 != step['diagnostics_sha256']):
                raise ValueError
            # Compare semantic values, including original detail bytes. Timestamp
            # formatting may differ after PostgreSQL normalizes an equivalent UTC value.
            from dataclasses import asdict
            def identity(result):
                return asdict(result) | {'checked_at': datetime.fromisoformat(result.checked_at)}
            actual = {(r.check_code,r.dataset_key):identity(r) for r in results}
            expected = {(r.check_code,r.dataset_key):identity(r) for r in (*report.results,*report.diagnostics)}
            if actual != expected:
                raise ValueError
            fields = ('dataset_key','storage_path','sha256','schema_fingerprint','byte_size',
                      'row_count','min_period','max_period')
            if sorted(tuple(row[k] for k in fields) for row in artifacts) != sorted(
                    tuple(getattr(entry,k) for k in fields) for entry in report.manifest.entries):
                raise ValueError
        return approval
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
        raise Problem(409, 'candidate_ineligible') from None


def stopped_failure(connection, run):
    """Require the current finished failure marker, not just an empty lease."""
    if (run['status'] != 'publication_failed' or run['worker_owner_id'] is not None
            or run['lease_until'] is not None):
        return False
    failure = connection.execute("""SELECT * FROM refresh_steps WHERE run_id=%s
        AND stage='publish' AND work_key='publication' AND attempt=%s""",
        (run['id'],run['publication_generation']+1)).fetchone()
    return bool(failure and failure['status']=='failed' and failure['finished_at']
                and failure['error_code'])


def actions(connection, run, version, warning):
    """Return the same conservative eligibility used by all command paths."""
    result = dict(approve=False, publication_retry=False, discard=False)
    if not run or not version or version['disposition'] != 'active':
        return result
    event = connection.execute('SELECT id FROM publication_events WHERE version_id=%s', (version['id'],)).fetchone()
    if event or run['status'] not in ('awaiting_approval','publication_failed') or run['lease_until'] is not None:
        return result
    # Failure writers clear ownership only after synchronous work stops, or
    # after operator lock proof. A legacy failure without that proof stays closed.
    if run['status'] == 'publication_failed' and not stopped_failure(connection,run):
        return result
    result['discard'] = True
    try:
        recorded(connection, run, version, require_approval=run['status'] != 'awaiting_approval')
    except Problem:
        return result
    result['approve'] = run['status'] == 'awaiting_approval' and version['approval_required']
    if run['status'] == 'publication_failed' and warning and warning['resolved_at'] is None:
        history = connection.execute("""SELECT code FROM failure_warnings WHERE run_id=%s AND stage='publish'
            UNION ALL SELECT error_code AS code FROM refresh_steps WHERE run_id=%s AND stage='publish'
            AND error_code IS NOT NULL""", (run['id'],run['id'])).fetchall()
        result['publication_retry'] = warning['code'] in RECOVERABLE and all(r['code'] in RECOVERABLE for r in history)
    return result
