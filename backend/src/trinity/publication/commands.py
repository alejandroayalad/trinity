"""Accept Admin approval, retry and discard without storage or queue I/O."""
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from trinity.contracts.manifest import canonical_json, sha256
from trinity.errors import Problem
from trinity.publication.checks import actions
from trinity.publication.service import PublicationService, locked
from trinity.refresh.repository import lock_control, read_command
from trinity.refresh.schemas import parse_command
from trinity.refresh.service import _authorize, _receipt


class PublicationCommands(PublicationService):
    """Serialize commands with publishers and retain exact acceptance receipts.

    Resolve current authority before parsing protected inputs or reading receipts.
    Matching replay precedes revision checks. Every accepted state change and its
    receipt commit together. The worker performs all later byte verification.
    """
    def command(self, token, version_id, action, raw, keys, etags, pairs=()):
        """Return an original receipt or apply one eligible candidate action."""
        fingerprint = sha256(canonical_json({}))
        with self.transaction() as c:
            actor = _authorize(c,token,'candidate:review' if action=='approve' else 'refresh:recover',lock=True)
            key = parse_command(raw,keys,pairs)
            try:
                parsed = UUID(version_id)
                if str(parsed) != version_id.lower():
                    raise ValueError
                version_id = parsed
            except (ValueError,TypeError,AttributeError):
                raise Problem(422,'invalid_request') from None
            lock_control(c)
            receipt = read_command(c,key)
            if receipt:
                if any(receipt[k] != value for k,value in (
                        ('actor_id',actor.user_id),('action',action),('target_id',version_id),
                        ('request_fingerprint',fingerprint))):
                    raise Problem(409,'idempotency_conflict')
                return _receipt(receipt,replayed=True)
            if not etags:
                raise Problem(428,'precondition_required')
            if len(etags)!=1 or re.fullmatch(r'"candidate-(0|[1-9][0-9]*)"',etags[0]) is None:
                raise Problem(422,'invalid_request')
            target = c.execute('SELECT run_id FROM data_versions WHERE id=%s',(version_id,)).fetchone()
            if not target:
                raise Problem(404,'resource_not_found')
            control,run,version,_ = locked(c,target['run_id'])
            if etags[0] != f'"candidate-{version["revision"]}"':
                raise Problem(412,'revision_mismatch')
            warning = c.execute('SELECT * FROM failure_warnings WHERE run_id=%s AND resolved_at IS NULL FOR UPDATE',
                                (run['id'],)).fetchone()
            setup = c.execute('SELECT setup_completed_at FROM shared_settings WHERE id=1').fetchone()
            if not setup or not setup['setup_completed_at']:
                raise Problem(409,'setup_required')
            if control['holder_run_id'] != run['id'] or not actions(c,run,version,warning).get(action):
                raise Problem(409,'candidate_ineligible')
            # Approval records evidence identity and actor together with intent.
            # It does not read storage or grant permission to skip worker checks.
            if action == 'approve':
                c.execute("""INSERT INTO approvals(id,version_id,approved_by,approved_at,manifest_sha256,
                    validation_step_id,review_warning_digest) VALUES(%s,%s,%s,clock_timestamp(),%s,%s,%s)""",
                    (uuid4(),version_id,actor.user_id,version['manifest_sha256'],version['validation_step_id'],version['review_warning_digest']))
                payload = dict(schema_version=1,job_kind='publish_version',run_id=str(run['id']),
                    version_id=str(version_id),publication_generation=run['publication_generation'],dispatch_generation=0)
                c.execute("""INSERT INTO job_outbox(id,run_id,job_kind,deduplication_key,payload)
                    VALUES(%s,%s,'publish_version',%s,%s)""",(uuid4(),run['id'],f'publish:{version_id}',Jsonb(payload)))
                c.execute("UPDATE refresh_runs SET status='publishing',revision=revision+1 WHERE id=%s",(run['id'],))
            # A retry keeps evidence and approval. Only its new generation grants
            # one more verifier invocation; old notifications lose authority.
            elif action == 'publication_retry':
                outbox = c.execute("SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='publish_version' FOR UPDATE",(run['id'],)).fetchone()
                if not outbox:
                    raise Problem(409,'candidate_ineligible')
                payload = dict(schema_version=1,job_kind='publish_version',run_id=str(run['id']),
                    version_id=str(version_id),publication_generation=run['publication_generation']+1,
                    dispatch_generation=outbox['dispatch_generation']+1)
                c.execute("""UPDATE job_outbox SET status='pending',payload=%s,dispatch_generation=dispatch_generation+1,
                    dispatch_attempts=0,available_at=clock_timestamp(),lease_token=NULL,lease_until=NULL,
                    delivered_at=NULL,last_error=NULL WHERE id=%s""",(Jsonb(payload),outbox['id']))
                c.execute("""UPDATE refresh_runs SET status='publishing',publication_generation=publication_generation+1,
                    execution_fence=execution_fence+1,revision=revision+1,worker_owner_id=NULL,lease_until=NULL,
                    error_code=NULL,error_summary=NULL WHERE id=%s""",(run['id'],))
            else:
                # Discard is permanent metadata abandonment. Retain all bytes and
                # history, invalidate old writers, and release only this owned slot.
                c.execute("""UPDATE data_versions SET disposition='discarded',discarded_at=clock_timestamp(),
                    discarded_by=%s WHERE id=%s""",(actor.user_id,version_id))
                c.execute("""UPDATE refresh_runs SET status='discarded',finished_at=clock_timestamp(),
                    execution_fence=execution_fence+1,revision=revision+1,worker_owner_id=NULL,lease_until=NULL WHERE id=%s""",(run['id'],))
                c.execute('UPDATE refresh_control SET holder_run_id=NULL,revision=revision+1 WHERE id=1')
            if warning:
                c.execute("""UPDATE failure_warnings SET resolved_at=clock_timestamp(),resolution=%s,resolved_by=%s
                    WHERE id=%s""",(action,actor.user_id,warning['id']))
            c.execute('UPDATE data_versions SET revision=revision+1 WHERE id=%s',(version_id,))
            receipt = c.execute("""INSERT INTO api_commands(id,idempotency_key,actor_id,action,target_id,
                request_fingerprint,accepted_at,run_id,version_id,result,status_url)
                VALUES(%s,%s,%s,%s,%s,%s,clock_timestamp(),%s,%s,%s,%s) RETURNING *""",
                (uuid4(),key,actor.user_id,action,version_id,fingerprint,run['id'],version_id,
                 'discarded' if action=='discard' else 'queued',f'/api/v1/refresh-runs/{run["id"]}'))
            result = _receipt(receipt.fetchone(),replayed=False)
        return result
