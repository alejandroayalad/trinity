"""Reconcile interrupted publication through explicit same-host operator custody."""
from datetime import UTC, datetime
from uuid import UUID

from psycopg.types.json import Jsonb

from trinity.errors import Problem
from trinity.publication.checks import actions, stopped_failure
from trinity.publication.custody import custody, check_access, CustodyError
from trinity.publication.service import PublicationService, locked, event_for, fail_stopped

FIELDS = ('run_status','version_id','publication_generation','execution_fence',
          'publication_event_id','warning_id','retry_eligible')


def result(run_id, outcome, reason=None, **values):
    """Return only the operator's documented safe fields."""
    return dict(outcome=outcome,run_id=str(run_id) if run_id else None,
                **{key:values.get(key) for key in FIELDS},reason_code=reason)


class PublicationRecovery(PublicationService):
    """Prove stop, then reconcile once without approving or scheduling new work."""
    def snapshot(self, c, run_id, outcome='inspected', reason=None):
        """Project one state snapshot; this read is never stop proof."""
        run = c.execute('SELECT * FROM refresh_runs WHERE id=%s',(run_id,)).fetchone()
        if not run:
            return result(run_id,'not_found'),None
        version = c.execute('SELECT * FROM data_versions WHERE run_id=%s',(run_id,)).fetchone()
        event = event_for(c,version)
        warning = c.execute('SELECT * FROM failure_warnings WHERE run_id=%s AND resolved_at IS NULL',(run_id,)).fetchone()
        eligible = actions(c,run,version,warning)['publication_retry']
        run['_safely_failed'] = stopped_failure(c,run)
        return result(run_id,outcome,reason,run_status=run['status'],
            version_id=str(version['id']) if version else None,
            publication_generation=run['publication_generation'],execution_fence=run['execution_fence'],
            publication_event_id=str(event['id']) if event else None,
            warning_id=str(warning['id']) if warning else None,retry_eligible=eligible),run

    def reconcile(self, run_id, root, *, inspect=False, generation=None, fence=None):
        """Hold lock proof through the failure transaction and return exact outcomes.

        A lost response is safe to repeat. An already committed publication never
        moves the active pointer; an already failed generation creates no warning.
        A later Admin generation always rejects an old operator target.
        """
        mutation = False
        try:
            with self.transaction(readonly=True) as c:
                current,run = self.snapshot(c,run_id)
            if not run:
                return current
            check_access(root,run)
            if inspect:
                return current
            if run['publication_generation'] != generation:
                return {**current,'outcome':'blocked','reason_code':'stale_target'}
            if current['publication_event_id']:
                return {**current,'outcome':'already_published'}
            if run['status']=='publication_failed':
                return {**current,'outcome':'already_failed' if run['_safely_failed'] else 'blocked',
                        'reason_code':None if run['_safely_failed'] else 'state_unknown'}
            if run['status']!='publishing' or not current['version_id']:
                return {**current,'outcome':'not_applicable'}
            with custody(root,run):
                with self.transaction() as c:
                    control,live,version,_ = locked(c,run_id)
                    if live['publication_generation'] != generation:
                        return self.snapshot(c,run_id,'blocked','stale_target')[0]
                    if event_for(c,version):
                        return self.snapshot(c,run_id,'already_published')[0]
                    if live['status']=='publication_failed':
                        safe = stopped_failure(c,live)
                        return self.snapshot(c,run_id,'already_failed' if safe else 'blocked',
                                             None if safe else 'state_unknown')[0]
                    if live['execution_fence'] != fence:
                        return self.snapshot(c,run_id,'blocked','stale_target')[0]
                    if (live['status']!='publishing' or control['holder_run_id']!=run_id
                            or version['disposition']!='active'
                            or live['worker_execution_ref'] != run['worker_execution_ref']):
                        return self.snapshot(c,run_id,'blocked','state_changed')[0]
                    outbox = c.execute("SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='publish_version' FOR UPDATE",(run_id,)).fetchone()
                    if not outbox:
                        return self.snapshot(c,run_id,'blocked','state_unknown')[0]
                    now = datetime.now(UTC)
                    if any(lease and lease>now for lease in (live['lease_until'],outbox['lease_until'])):
                        return self.snapshot(c,run_id,'blocked','lease_not_expired')[0]
                    # Expiry limits stale dispatch; only the held inode proves stop.
                    payload = {**outbox['payload'],'dispatch_generation':outbox['dispatch_generation']+1}
                    c.execute("""UPDATE job_outbox SET status='pending',dispatch_generation=dispatch_generation+1,
                        payload=%s,lease_token=NULL,lease_until=NULL,delivered_at=NULL WHERE id=%s""",(Jsonb(payload),outbox['id']))
                    mutation = True
                    fail_stopped(c,live,version,'publication_interrupted')
                    outcome = self.snapshot(c,run_id,'recovered_failure')[0]
                return outcome
        except CustodyError as error:
            return {**current,'outcome':'blocked','reason_code':error.code}
        except Exception:
            # Do not assert rollback after a network failure during COMMIT.
            return result(run_id,'outcome_unknown' if mutation else 'dependency_unavailable',
                          'database_unavailable')


def cli(argv):
    """Run before Redis, S3 or EIA initialization; never print raw exceptions."""
    import argparse
    import json
    import os
    from trinity.adapters.postgres import Database
    from trinity.config import load_api_settings

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError('invalid_input')
    parser = Parser(prog='publication-recover',description=(
        'Inspect or reconcile one publication on its trusted worker host. '
        'Recovery proves stop with the original lock. It never kills, approves or retries. '
        'After recovered_failure, an Admin must request publication-retry or discard.'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--inspect',action='store_true')
    parser.add_argument('--expected-generation',type=int)
    parser.add_argument('--expected-fence',type=int)
    identifier = None
    try:
        args = parser.parse_args(argv)
        identifier = UUID(args.run_id)
        if str(identifier)!=args.run_id or (args.inspect and (args.expected_generation is not None or args.expected_fence is not None)):
            raise ValueError
        if not args.inspect and (args.expected_generation is None or args.expected_fence is None
                                or args.expected_generation<0 or args.expected_fence<0):
            raise ValueError
    except (ValueError,TypeError):
        print(json.dumps(result(identifier,'invalid_input','invalid_arguments')))
        return 2
    database = None
    try:
        database = Database(load_api_settings())
        database.open()
        value = PublicationRecovery(database).reconcile(identifier,os.environ['TRINITY_REFRESH_ROOT'],
            inspect=args.inspect,generation=args.expected_generation,fence=args.expected_fence)
    except Exception:
        value = result(identifier,'dependency_unavailable','configuration_unavailable')
    finally:
        if database:
            database.close()
    print(json.dumps(value))
    return {'inspected':0,'recovered_failure':0,'already_failed':0,'already_published':0,
            'invalid_input':2,'not_found':2,'not_applicable':2,'blocked':3,
            'dependency_unavailable':4,'outcome_unknown':4}[value['outcome']]
