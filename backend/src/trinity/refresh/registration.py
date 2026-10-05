"""Register verified preparation evidence and hand off the candidate atomically.

The worker supplies a reserved run, candidate and validation step with its
current execution fence. Verify saved preparation outside SQL transactions.
Then persist artifacts, checks, Preview's identities and either review state
or publication intent together. The active publication is never changed here.
"""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from trinity.adapters.postgres import Deadline
from trinity.contracts.manifest import read_json, sha256
from trinity.errors import Problem
from trinity.refresh.evidence import load_candidate


def _owned(connection, run_id, version_id, step_id, fence):
    """Lock in canonical order and reject a stale or unrelated writer."""
    control = connection.execute('SELECT * FROM refresh_control WHERE id=1 FOR UPDATE').fetchone()
    run = connection.execute('''SELECT *,lease_until>clock_timestamp() AS lease_valid,
        (execution_deadline_at IS NULL OR execution_deadline_at>clock_timestamp()) AS in_time,
        (registration_deadline_at IS NULL OR registration_deadline_at>clock_timestamp()) AS registration_live
        FROM refresh_runs WHERE id=%s FOR UPDATE''', (run_id,)).fetchone()
    version = connection.execute('SELECT * FROM data_versions WHERE id=%s FOR UPDATE', (version_id,)).fetchone()
    step = connection.execute('SELECT * FROM refresh_steps WHERE id=%s FOR UPDATE', (step_id,)).fetchone()
    if (not control or control['holder_run_id'] != run_id or not run or not version or not step
            or run['execution_fence'] != fence
            or run['status'] not in ('running','awaiting_approval','publishing')
            or (run['status'] == 'running' and
                (run['lease_valid'] is not True or not run['in_time'] or not run['registration_live']))
            or (run['status'] != 'running' and version['preparation_receipt_sha256'] is None)
            or version['run_id'] != run_id or version['disposition'] != 'active'
            or step['run_id'] != run_id or step['stage'] != 'validate'
            or step['execution_fence'] != fence):
        raise Problem(409, 'candidate_ineligible')
    return run, version, step


def _binding(run, version, step, evidence):
    """Compare the measured candidate to the worker's frozen expectations."""
    report = evidence.report
    manifest = report.manifest
    policy = run['policy_snapshot']
    if (manifest.version_id != str(version['id'])
            or manifest.requested_start != run['requested_start']
            or manifest.requested_end != run['requested_end'] or run['window_frozen_at'] is None
            or version['coverage_start'] != manifest.requested_start
            or version['coverage_end'] != manifest.requested_end
            or version['latest_observation_date'] != max(
                entry.max_period for entry in manifest.entries if entry.dataset_key == 'national')
            or version['contract_version'] != 'trinity-data-v1'
            or version['validation_checkset'] != 'trinity-data-v1'
            or any(policy.get(key) != value for key, value in {
                'workflow_policy':'warnings-v1', 'diagnostic_registry':'warnings-v1',
                'contract_version':'trinity-data-v1', 'validation_checkset':'trinity-data-v1',
                'settings_revision':run['settings_revision'],
                'requested_start':run['requested_start'].isoformat(),
            }.items())
            or step['validation_attempt_id'] != UUID(report.attempt_id)
            or version['manifest_sha256'] != manifest.digest
            or policy.get('end_strategy') not in ('latest_national','fixed')
            or (policy.get('end_strategy') == 'fixed'
                and policy.get('explicit_end') != run['requested_end'].isoformat())):
        raise Problem(409, 'candidate_ineligible')


def persist_candidate(connection, run_id, version_id, step_id, fence, evidence):
    """Write one verified handoff on the caller's transaction; never commit here.

    This internal persistence helper accepts evidence produced by load_candidate.
    The service below is the verification entry point. Exact replay checks the
    persisted bindings; a new receipt cannot replace accepted candidate evidence.
    """
    run, version, step = _owned(connection, run_id, version_id, step_id, fence)
    _binding(run, version, step, evidence)
    report, receipt = evidence.report, evidence.receipt
    target = 'awaiting_approval' if report.approval_required else 'publishing'
    if version['preparation_receipt_sha256'] is not None:
        if (version['preparation_receipt_sha256'] != evidence.preparation_receipt_sha256
                or version['evidence_bundle_sha256'] != receipt.bundle_sha256
                or version['validation_attempt_id'] != UUID(report.attempt_id)
                or version['validation_step_id'] != step_id or run['status'] != target
                or step['validation_sha256'] != report.validation_sha256
                or step['diagnostics_sha256'] != report.diagnostics_sha256):
            raise Problem(409, 'candidate_ineligible')
        return target
    if (run['status'] != 'running' or version['status'] not in ('preparing','validating')
            or step['status'] not in ('running','succeeded')):
        raise Problem(409, 'candidate_ineligible')

    # Store all measured analytical files. The complete bundle remains pinned
    # through Preview's existing column, rather than a second competing field.
    for entry in report.manifest.entries:
        connection.execute("""INSERT INTO dataset_artifacts(id,version_id,dataset_key,storage_path,
            sha256,schema_fingerprint,byte_size,row_count,min_period,max_period)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid4(),version_id,entry.dataset_key,entry.storage_path,entry.sha256,entry.schema_fingerprint,
             entry.byte_size,entry.row_count,entry.min_period,entry.max_period))
    for result in (*report.results, *report.diagnostics):
        connection.execute("""INSERT INTO validation_results(id,version_id,step_id,manifest_sha256,
            checkset_version,check_code,check_revision,dataset_key,required,severity,status,
            checked_count,failed_count,details,details_path,details_sha256,checked_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid4(),version_id,step_id,result.manifest_sha256,result.checkset_version,
             result.check_code,result.check_revision,result.dataset_key,result.required,result.severity,
             result.status,result.checked_count,result.failed_count,Jsonb(read_json(result.details_json)),
             result.details_path,sha256(result.details_json),result.checked_at))
    connection.execute("""UPDATE refresh_steps SET status='succeeded',
        finished_at=COALESCE(finished_at,clock_timestamp()),processed_count=39,total_count=39,
        validation_sha256=%s,diagnostics_sha256=%s WHERE id=%s""",
        (report.validation_sha256,report.diagnostics_sha256,step_id))
    latest = max(entry.max_period for entry in report.manifest.entries if entry.dataset_key == 'national')
    connection.execute("""UPDATE data_versions SET status='validated',revision=revision+1,
        validated_at=clock_timestamp(),validation_step_id=%s,validation_attempt_id=%s,
        evidence_bundle_sha256=%s,preparation_receipt_sha256=%s,storage_verified_at=clock_timestamp(),
        approval_required=%s,review_warning_count=%s,review_warning_digest=%s,
        diagnostics_frozen_at=clock_timestamp(),latest_observation_date=%s WHERE id=%s""",
        (step_id,UUID(report.attempt_id),receipt.bundle_sha256,evidence.preparation_receipt_sha256,
         report.approval_required,report.warning_count,report.warning_digest,latest,version_id))
    if target == 'publishing':
        connection.execute("""INSERT INTO job_outbox(id,run_id,job_kind,deduplication_key,payload)
            VALUES(%s,%s,'publish_version',%s,%s)""",
            (uuid4(),run_id,f'publish:{version_id}',Jsonb({'schema_version':1,'run_id':str(run_id),
             'version_id':str(version_id),'job_kind':'publish_version',
             'publication_generation':run['publication_generation'],'dispatch_generation':0})))
    # Waiting review and publication intent retain admission, but no longer
    # grant this preparation worker an active execution lease.
    connection.execute('UPDATE refresh_runs SET status=%s,revision=revision+1,lease_until=NULL WHERE id=%s',
                       (target,run_id))
    return target


class CandidateRegistration:
    """Verify outside SQL, then commit the complete evidence and routing result."""
    def __init__(self, database):
        self.database = database

    def register(self, *, run_id, version_id, step_id, fence, root, receipt_sha256,
                 storage, timeout_seconds=30):
        """Reject stale ownership before reads and recheck it before commit.

        No public endpoint accepts root or receipt hashes. These come from the
        trusted supervisor. Storage failure preserves the old publication and
        all available evidence; the worker records its bounded failure later.
        """
        deadline_at = None
        if root.name != str(version_id):
            raise Problem(409, 'candidate_ineligible')
        with self.database.transaction(Deadline(), error_code='dependency_unavailable') as connection:
            run, _, _ = _owned(connection,run_id,version_id,step_id,fence)
            if run['status'] == 'running':
                # Save the first verification deadline before remote I/O. A
                # recovered owner consumes another attempt inside this budget.
                # Neither another delivery nor a crash can add thirty seconds.
                if run['registration_attempts'] >= 3:
                    raise Problem(409, 'candidate_ineligible')
                budget = connection.execute('''UPDATE refresh_runs SET
                    registration_deadline_at=COALESCE(registration_deadline_at,
                        LEAST(execution_deadline_at,clock_timestamp()+%s*interval '1 second')),
                    registration_attempts=registration_attempts+1 WHERE id=%s
                    RETURNING registration_deadline_at''', (min(30,timeout_seconds),run_id)).fetchone()
                deadline_at = budget['registration_deadline_at']
                timeout_seconds = min(timeout_seconds,
                    (deadline_at-datetime.now(UTC)).total_seconds())
        evidence = load_candidate(root,receipt_sha256,storage,timeout_seconds=timeout_seconds)
        # Bound the final transaction and its commit by the same saved budget.
        # Verification may have consumed almost all of the original allowance.
        remaining = (deadline_at-datetime.now(UTC)).total_seconds() if deadline_at else timeout_seconds
        with self.database.transaction(Deadline(min(15,remaining)), error_code='dependency_unavailable') as connection:
            return persist_candidate(connection,run_id,version_id,step_id,fence,evidence)
