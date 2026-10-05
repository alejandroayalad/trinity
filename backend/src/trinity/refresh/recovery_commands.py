"""Resolve failed lifecycle intent atomically after durable proof of writer stop."""
import re
from uuid import UUID, uuid4

from trinity.adapters.postgres import Deadline
from trinity.contracts.manifest import canonical_json, sha256
from trinity.errors import Problem
from trinity.publication.checks import stopped_failure
from trinity.publication.service import locked
from trinity.refresh.repository import accept_run, lock_control, read_command
from trinity.refresh.schemas import parse_command
from trinity.refresh.service import _authorize, _receipt
from trinity.settings.repository import read_settings


def recoverable(connection, run, version, warning):
    """Require the same stop evidence that the existing workers record."""
    if not run or not warning or warning['resolved_at'] is not None or warning['run_id'] != run['id']:
        return False
    if version and (version['disposition'] != 'active' or connection.execute(
            'SELECT id FROM publication_events WHERE version_id=%s', (version['id'],)).fetchone()):
        return False
    if run['status'] == 'publication_failed':
        return stopped_failure(connection, run)
    if run['status'] != 'failed' or not run['finished_at'] or run['lease_until'] is not None:
        return False
    # Dispatch failure has no child. Preparation failure retains its confirmed
    # child_stopped flag even when the historical owner ID remains on the run.
    return (run['worker_owner_id'] is None or
            (run['worker_execution_ref'] or {}).get('child_stopped') is True)


class RecoveryCommands:
    """Recheck authority, replay exact intent, then resolve or replace one run."""
    def __init__(self, database):
        self.database = database

    def command(self, token, run_id, action, raw, keys, etags, pairs=()):
        """Retain warnings/candidates/history; delete warning means soft resolution."""
        fingerprint = sha256(canonical_json({}))
        with self.database.transaction(Deadline(), error_code='dependency_unavailable') as connection:
            _authorize(connection, token, 'refresh:recover')
            if action not in ('rerun', 'delete_warning'):
                raise Problem(422, 'invalid_request')
            if action == 'delete_warning' and raw:
                raise Problem(422, 'invalid_request')
            key = parse_command(b'{}' if action == 'delete_warning' else raw, keys, pairs)
            try:
                target = UUID(run_id)
                if str(target) != run_id.lower():
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise Problem(422, 'invalid_request') from None
            lock_control(connection)
            actor = _authorize(connection, token, 'refresh:recover', lock=True)
            previous = read_command(connection, key)
            if previous:
                if any(previous[name] != value for name, value in (
                        ('actor_id', actor.user_id), ('action', action), ('target_id', target),
                        ('request_fingerprint', fingerprint))):
                    raise Problem(409, 'idempotency_conflict')
                return _receipt(previous, replayed=True)
            if not etags:
                raise Problem(428, 'precondition_required')
            if len(etags) != 1 or not re.fullmatch(r'"run-(0|[1-9][0-9]*)"', etags[0]):
                raise Problem(422, 'invalid_request')
            control, run, version, _ = locked(connection, target)
            if etags[0] != f'"run-{run["revision"]}"':
                raise Problem(412, 'revision_mismatch')
            warning = connection.execute('SELECT * FROM failure_warnings WHERE run_id=%s AND resolved_at IS NULL FOR UPDATE', (target,)).fetchone()
            if control['holder_run_id'] != target or not recoverable(connection, run, version, warning):
                raise Problem(409, 'action_not_allowed')
            connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR SHARE')
            settings = read_settings(connection)
            if settings['setup_completed_at'] is None:
                raise Problem(409, 'setup_required')
            if version:
                connection.execute("""UPDATE data_versions SET disposition='discarded',discarded_at=clock_timestamp(),
                    discarded_by=%s,revision=revision+1 WHERE id=%s""", (actor.user_id, version['id']))
            connection.execute("""UPDATE refresh_runs SET status='failed',finished_at=COALESCE(finished_at,clock_timestamp()),
                worker_owner_id=NULL,lease_until=NULL,execution_fence=execution_fence+1,revision=revision+1 WHERE id=%s""", (target,))
            connection.execute("""UPDATE failure_warnings SET resolved_at=clock_timestamp(),resolution=%s,resolved_by=%s
                WHERE id=%s""", (action, actor.user_id, warning['id']))
            connection.execute('UPDATE refresh_control SET holder_run_id=NULL,revision=revision+1 WHERE id=1')
            if action == 'rerun':
                receipt = accept_run(connection, actor.user_id, key, fingerprint, settings)
                connection.execute("UPDATE refresh_runs SET trigger_kind='rerun',rerun_of_run_id=%s WHERE id=%s", (target, receipt['run_id']))
                receipt = connection.execute("UPDATE api_commands SET action='rerun',target_id=%s WHERE id=%s RETURNING *", (target, receipt['id'])).fetchone()
            else:
                receipt = connection.execute("""INSERT INTO api_commands(id,idempotency_key,actor_id,action,target_id,
                    request_fingerprint,accepted_at,run_id,version_id,result,status_url)
                    VALUES(%s,%s,%s,'delete_warning',%s,%s,clock_timestamp(),%s,%s,'warning_resolved',%s) RETURNING *""",
                    (uuid4(), key, actor.user_id, target, fingerprint, target, version['id'] if version else None,
                     f'/api/v1/refresh-runs/{target}')).fetchone()
            result = _receipt(receipt, replayed=False)
        return result
