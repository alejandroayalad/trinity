"""Accept failed-run recovery and describe eligibility from retained evidence.

An authorized Admin supplies command identity and the failed run revision. One
service-owned transaction rechecks authority, serializes admission, replays an
existing receipt or abandons safely stopped work. Rerun also admits a linked new
run with current settings; warning resolution starts nothing. Return acceptance
only after commit. Errors roll back all effects and preserve the old blocker.

The shared eligibility helper performs database reads only. Read callers supply
one consistent snapshot; command callers hold lifecycle locks. Neither these
flags nor an expired lease establishes permission to skip confirmed-stop proof.
No storage or queue calls occur in this module.
"""

from trinity.publication.checks import stopped_failure
from trinity.refresh.dispatch import MAX_ATTEMPTS


def _refresh_stopped(connection, run, version):
    """Recognize only failure shapes produced by the current Refresh writers.

    A pre-claim failure has no execution history. A started failure needs the
    trusted child's stop marker bound to the retained owner. A passed deadline
    or an empty lease alone never establishes that storage writes have stopped.
    """
    if run['finished_at'] is None or run['lease_until'] is not None:
        return False
    steps = connection.execute("""SELECT
        EXISTS(SELECT 1 FROM refresh_steps WHERE run_id=%s) AS has_steps,
        EXISTS(SELECT 1 FROM refresh_steps WHERE run_id=%s AND status='running')
            AS has_running_steps""", (run['id'], run['id'])).fetchone()
    if not steps or steps['has_running_steps']:
        return False
    ref = run['worker_execution_ref']
    if run['started_at'] is not None:
        # ExecutionService.reference/fail persist these values only while the
        # supplied owner and fence still match. Recovery changes the owner when
        # it takes a new fence. There is no separate fence field in the JSON.
        return bool(
            run['worker_owner_id'] is not None and run['execution_fence'] > 0
            and isinstance(ref, dict) and ref.get('child_stopped') is True
            and ref.get('owner') == str(run['worker_owner_id'])
            and (ref.get('version_id') is None
                 or (version is not None and ref['version_id'] == str(version['id'])))
            and run['error_code'] in ('refresh_failed', 'stage_timeout', 'worker_lost')
            and (version is None or version['status'] == 'rejected')
        )
    # Dispatch exhaustion and policy rejection can occur before any child is
    # started. Their terminal state prevents a delayed queue job from claiming.
    if (version is not None or steps['has_steps'] or ref not in (None, {})
            or run['worker_owner_id'] is not None or run['execution_fence'] != 0):
        return False
    outbox = connection.execute("""SELECT * FROM job_outbox
        WHERE run_id=%s AND job_kind='refresh_pipeline'""", (run['id'],)).fetchone()
    if not outbox:
        return False
    attempts = outbox['dispatch_attempts']
    if run['error_code'] == 'dispatch_failed':
        return attempts >= MAX_ATTEMPTS
    return run['error_code'] == 'refresh_failed' and attempts >= 1


def recovery_actions(connection, settings, control, run, version, warning):
    """Return rerun/delete flags for the currently retained failed lifecycle.

    Require a matching unresolved warning and admission owner before reading
    stop evidence. Preserve publications and inactive candidates. Publication
    failures reuse their existing stop check; Refresh failures use their own
    recorded proof. Missing setup disables rerun but not safe warning removal.
    Database errors propagate to the owning service's safe transaction wrapper.
    """
    disabled = {'rerun': False, 'delete_warning': False}
    if (not run or not control or not warning
            or control['holder_run_id'] != run['id']
            or run['status'] not in ('failed', 'publication_failed')
            or warning['run_id'] != run['id']
            or any(warning[name] is not None
                   for name in ('resolved_at', 'resolution', 'resolved_by'))
            or not run['error_code'] or warning['code'] != run['error_code']):
        return disabled
    if warning['version_id'] != (version['id'] if version else None):
        return disabled
    if version:
        if version['run_id'] != run['id'] or version['disposition'] != 'active':
            return disabled
        # Even a stale active pointer must not make a published candidate
        # abandonable. The immutable event, rather than only the pointer, wins.
        event = connection.execute('SELECT id FROM publication_events WHERE version_id=%s',
                                   (version['id'],)).fetchone()
        if event:
            return disabled
    if run['status'] == 'publication_failed':
        safe = (version is not None and warning['stage'] == 'publish'
                and run['finished_at'] is None and stopped_failure(connection, run))
    else:
        safe = warning['stage'] != 'publish' and _refresh_stopped(connection, run, version)
    if not safe:
        return disabled
    return {'rerun': bool(settings and settings['setup_completed_at'] is not None),
            'delete_warning': True}


class RecoveryService:
    """Coordinate recovery repositories inside one bounded transaction."""

    def __init__(self, database):
        self.database = database

    def command(self, token, run_id, action, raw, keys, etags, pairs=()):
        """Replay authorized intent or atomically resolve the targeted failure.

        Current authority precedes protected reads. Syntax is checked before
        receipt replay; a valid but obsolete revision is accepted on matching
        replay only. New intent must pass locked revision and stop checks.
        A rerun receipt points to the new run but stays bound to the old target.
        """
        from trinity.adapters.postgres import Deadline
        from trinity.contracts.manifest import canonical_json, sha256
        from trinity.errors import Problem
        from trinity.refresh import repository
        from trinity.refresh.schemas import parse_recovery_command
        from trinity.refresh.service import _authorize, _receipt
        from trinity.settings.repository import read_settings

        fingerprint = sha256(canonical_json({}))
        try:
            with self.database.transaction(Deadline(), error_code='dependency_unavailable') as connection:
                _authorize(connection, token, 'refresh:recover')
                command = parse_recovery_command(run_id, action, raw, keys, etags, pairs)
                control = repository.lock_control(connection)
                actor = _authorize(connection, token, 'refresh:recover', lock=True)
                previous = repository.read_command(connection, command.key)
                if previous is not None:
                    identity = (('actor_id', actor.user_id), ('action', command.action),
                                ('target_id', command.run_id), ('request_fingerprint', fingerprint))
                    if any(previous[name] != value for name, value in identity):
                        raise Problem(409, 'idempotency_conflict')
                    result = _receipt(previous, replayed=True)
                else:
                    # Share-lock current settings before target rows, matching
                    # manual/scheduled admission. Delete only reads settings;
                    # resolving a warning does not require completed setup.
                    if command.action == 'rerun':
                        connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR SHARE')
                    settings = read_settings(connection)
                    run, version, warning = repository.lock_recovery_target(connection, command.run_id)
                    if command.revision != str(run['revision']):
                        raise Problem(412, 'revision_mismatch')
                    if command.action == 'rerun' and settings['setup_completed_at'] is None:
                        raise Problem(409, 'setup_required')
                    if not recovery_actions(connection, settings, control, run, version, warning)[command.action]:
                        raise Problem(409, 'action_not_allowed')
                    repository.abandon_failed(connection, actor.user_id, command.action, run, version, warning)
                    if command.action == 'rerun':
                        receipt = repository.accept_run(connection, actor.user_id, command.key,
                            fingerprint, settings, rerun_of_run_id=command.run_id)
                    else:
                        receipt = repository.record_warning_resolution(
                            connection, actor.user_id, command, fingerprint, version)
                    result = _receipt(receipt, replayed=False)
            # Commit can itself fail. Do not report acceptance from inside the
            # context manager, even when all individual SQL statements passed.
            return result
        except Problem as error:
            if error.status == 503 and error.code == 'dependency_unavailable':
                raise Problem(503, error.code, retry_after=1) from None
            raise
