"""Check recovery orchestration and HTTP contracts with controlled repositories.

These tests run the real service, authorization policy and route adapters. The
transaction double proves service ordering and error propagation, not PostgreSQL
rollback or worker termination. Opt-in database cases test the SQL separately.
"""
from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from trinity.auth.permissions import Principal
from trinity.errors import Problem
from trinity.main import create_app
from trinity.publication.commands import PublicationCommands
from trinity.refresh.recovery import RecoveryService
from trinity.refresh.service import RefreshService, admin_context
from trinity.refresh.tracking import run_view


class CommandDatabase:
    """Track transaction lifetime and inject a failure at the commit boundary."""

    def __init__(self):
        self.events = []
        self.fail_commit = False
        self.connection = Mock()
        self.connection.execute.side_effect = self.execute

    def execute(self, sql, params=()):
        """Record auth/settings lock requests; repositories are separate doubles."""
        self.events.append('user_lock' if 'local_users' in sql else 'settings_lock')
        return Mock()

    @contextmanager
    def transaction(self, *args, **kwargs):
        """Do not report a commit after an exception or injected commit failure."""
        self.events.append('begin')
        try:
            yield self.connection
            if self.fail_commit:
                raise Problem(503, 'dependency_unavailable')
        except Exception:
            self.events.append('rollback')
            raise
        else:
            self.events.append('commit')


class RecoveryServiceTests(unittest.TestCase):
    """Keep state loading controlled while exercising all command decisions."""

    def setUp(self):
        self.now = datetime.now(UTC)
        self.db = CommandDatabase()
        self.actor = Principal('test_admin', 'admin', uuid4())
        self.run_id, self.key, self.new_id = uuid4(), uuid4(), uuid4()
        self.run = dict(id=self.run_id, revision=7)
        self.version = dict(id=uuid4())
        self.warning = dict(id=uuid4())
        self.settings = dict(setup_completed_at=self.now, revision=6)
        self.receipt = dict(id=uuid4(), actor_id=self.actor.user_id, action='rerun', target_id=self.run_id,
                            request_fingerprint=None, accepted_at=self.now, run_id=self.new_id,
                            version_id=None, status_url=f'/api/v1/refresh-runs/{self.new_id}', result='queued')
        self.resolve = self.mock('trinity.auth.repository.resolve_session', self.authorize)
        self.control = self.mock('trinity.refresh.repository.lock_control', self.lock_control)
        self.previous = self.mock('trinity.refresh.repository.read_command', lambda *args: None)
        self.read_settings = self.mock('trinity.settings.repository.read_settings', lambda *args: self.settings)
        self.target = self.mock('trinity.refresh.repository.lock_recovery_target', self.load_target)
        self.allowed = self.mock('trinity.refresh.recovery.recovery_actions', lambda *args: dict(rerun=True, delete_warning=True))
        self.abandon = self.mock('trinity.refresh.repository.abandon_failed', self.abandon_target)
        self.accept = self.mock('trinity.refresh.repository.accept_run', self.accept_new)
        self.record = self.mock('trinity.refresh.repository.record_warning_resolution', self.resolve_warning)
        self.service = RecoveryService(self.db)

    def mock(self, name, effect):
        """Restore every repository seam after its individual test."""
        patcher = patch(name, side_effect=effect)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def authorize(self, connection, token, *, lock=False):
        """Supply current identities; production require() still checks the role."""
        self.assertIs(connection, self.db.connection)
        self.db.events.append('auth_locked' if lock else 'auth')
        return self.actor

    def lock_control(self, connection):
        """Represent the serialized admission row without a real database."""
        self.assertIs(connection, self.db.connection)
        self.db.events.append('control')
        return dict(holder_run_id=self.run_id)

    def load_target(self, connection, run_id):
        """Fail tests that substitute the new run for the recovery target."""
        self.assertIs(connection, self.db.connection)
        self.assertEqual(run_id, self.run_id)
        self.db.events.append('target')
        return self.run, self.version, self.warning

    def abandon_target(self, connection, actor_id, action, run, version, warning):
        """Ensure abandonment and admission use the same transaction connection."""
        self.assertIs(connection, self.db.connection)
        self.assertIs(run, self.run)
        self.db.events.append('abandon')

    def accept_new(self, connection, actor_id, key, fingerprint, settings, *, rerun_of_run_id):
        """Return acceptance linked to a new run using the current settings row."""
        self.assertIs(connection, self.db.connection)
        self.assertIs(settings, self.settings)
        self.assertEqual(rerun_of_run_id, self.run_id)
        self.db.events.append('admit')
        self.receipt['request_fingerprint'] = fingerprint
        return self.receipt

    def resolve_warning(self, connection, actor_id, command, fingerprint, version):
        """Deletion tracks old work and does not reuse the rerun admission seam."""
        self.assertIs(connection, self.db.connection)
        self.db.events.append('resolve')
        return self.receipt | dict(action='delete_warning', run_id=self.run_id,
            status_url=f'/api/v1/refresh-runs/{self.run_id}', result='warning_resolved',
            version_id=self.version['id'], request_fingerprint=fingerprint)

    def command(self, action='rerun', **changes):
        """Submit valid input unless a test changes one field."""
        values = dict(token='t'*43, run_id=str(self.run_id), action=action,
                      raw=b'{}' if action=='rerun' else b'', keys=[str(self.key)], etags=['"run-7"'])
        return self.service.command(**(values | changes))

    def test_rerun_uses_current_settings_and_returns_only_after_commit(self):
        result = self.command()
        self.assertEqual(result.run_id, self.new_id)
        self.assertFalse(result.replayed)
        self.assertEqual(self.db.events[-1], 'commit')
        self.assertLess(self.db.events.index('control'), self.db.events.index('user_lock'))
        self.assertLess(self.db.events.index('settings_lock'), self.db.events.index('target'))
        self.assertLess(self.db.events.index('abandon'), self.db.events.index('admit'))
        self.record.assert_not_called()

    def test_delete_tracks_old_run_without_admission_or_settings_lock(self):
        self.settings['setup_completed_at'] = None
        result = self.command('delete_warning')
        self.assertEqual((result.run_id, result.result), (self.run_id, 'warning_resolved'))
        self.accept.assert_not_called()
        self.assertNotIn('settings_lock', self.db.events)
        self.assertEqual(self.db.events[-1], 'commit')

    def test_replay_precedes_stale_state_and_settings_checks(self):
        original = self.command()
        self.previous.side_effect = None
        self.previous.return_value = self.receipt
        self.run['revision'] = 30
        self.settings['setup_completed_at'] = None
        self.target.reset_mock()
        self.accept.reset_mock()
        self.abandon.reset_mock()
        replay = self.command(etags=['"run-1"'])
        self.assertEqual(replay.model_dump(), original.model_dump() | {'replayed': True})
        self.target.assert_not_called()
        self.accept.assert_not_called()
        self.abandon.assert_not_called()

    def test_replay_rechecks_authority_before_receipt_read(self):
        self.command()
        self.previous.reset_mock()
        self.actor = Principal('test_admin', 'viewer', self.actor.session_id)
        with self.assertRaises(Problem) as failure:
            self.command()
        self.assertEqual(failure.exception.status, 403)
        self.previous.assert_not_called()

    def test_conflicting_key_never_loads_another_target(self):
        self.command()
        self.previous.side_effect = None
        baseline = self.receipt.copy()
        self.target.reset_mock()
        for field, value in (('actor_id','someone_else'), ('action','delete_warning'),
                             ('target_id',uuid4()), ('request_fingerprint','different')):
            self.previous.return_value = baseline | {field:value}
            with self.subTest(field=field), self.assertRaises(Problem) as failure:
                self.command()
            self.assertEqual((failure.exception.status, failure.exception.code), (409,'idempotency_conflict'))
        self.target.assert_not_called()

    def test_stale_revision_setup_and_ineligible_state_have_no_mutation(self):
        for reason in ('revision', 'setup', 'state'):
            self.run['revision'] = 8 if reason=='revision' else 7
            self.settings['setup_completed_at'] = None if reason=='setup' else self.now
            self.allowed.side_effect = lambda *args: dict(rerun=reason!='state', delete_warning=True)
            with self.subTest(reason=reason), self.assertRaises(Problem) as failure:
                self.command()
            self.assertEqual(failure.exception.status, 412 if reason=='revision' else 409)
        self.abandon.assert_not_called()
        self.accept.assert_not_called()

    def test_role_and_session_changes_between_authorization_checks_are_denied(self):
        for second in (Principal('test_admin','analyst',self.actor.session_id), Problem(401,'invalid_session')):
            self.resolve.side_effect = [self.actor, self.actor, second]
            with self.subTest(second=type(second).__name__), self.assertRaises(Problem):
                self.command()
        self.target.assert_not_called()
        self.abandon.assert_not_called()

    def test_each_service_mutation_boundary_and_commit_error_roll_back(self):
        # The real SQL rollback cases are opt-in. Here every seam failure must
        # leave the service context via rollback and must not return acceptance.
        for seam in (self.abandon, self.accept):
            original = seam.side_effect
            seam.side_effect = Problem(503,'dependency_unavailable')
            with self.assertRaises(Problem) as failure:
                self.command()
            self.assertEqual(failure.exception.retry_after, 1)
            self.assertEqual(self.db.events[-1], 'rollback')
            seam.side_effect = original
        self.record.side_effect = Problem(503,'dependency_unavailable')
        with self.assertRaises(Problem):
            self.command('delete_warning')
        self.db.fail_commit = True
        with self.assertRaises(Problem):
            self.command()
        self.assertEqual(self.db.events[-1], 'rollback')

    def test_invalid_input_is_rejected_before_protected_state_reads(self):
        for changes in (dict(raw=b'{"force":true}'), dict(etags=[]), dict(run_id='bad'), dict(pairs=[('force','true')])):
            with self.subTest(changes=changes), self.assertRaises(Problem):
                self.command(**changes)
        self.control.assert_not_called()
        self.target.assert_not_called()

    def test_missing_target_is_safe_not_found(self):
        self.target.side_effect = Problem(404,'resource_not_found')
        with self.assertRaises(Problem) as failure:
            self.command()
        self.assertEqual(failure.exception.status,404)
        self.abandon.assert_not_called()

    def test_candidate_replay_uses_control_before_current_authority_locks(self):
        # Keep existing candidate replay semantics while proving its lock order
        # is now compatible with Start and recovery on the same session.
        candidate_id = uuid4()
        from trinity.contracts.manifest import canonical_json, sha256
        receipt = self.receipt | dict(action='discard', target_id=candidate_id,
            request_fingerprint=sha256(canonical_json({})), result='discarded')
        with patch('trinity.publication.commands.read_command', return_value=receipt), \
             patch('trinity.publication.commands.lock_control', side_effect=self.lock_control):
            result = PublicationCommands(self.db).command('t'*43,str(candidate_id),'discard',b'{}',[str(self.key)],[])
        self.assertTrue(result.replayed)
        self.assertLess(self.db.events.index('control'), self.db.events.index('user_lock'))

    def client(self):
        """Use the real route/service with controlled state, without opening SQL."""
        return TestClient(create_app(service=object(), refresh_service=RefreshService(self.db)))

    def headers(self):
        """Use a synthetic opaque token; production bearer syntax still applies."""
        return {'Authorization':'Bearer '+'t'*43,'Idempotency-Key':str(self.key),'If-Match':'"run-7"'}

    def test_http_rerun_receipt_headers_and_replay(self):
        with self.client() as client:
            url=f'/api/v1/refresh-runs/{self.run_id}/rerun'
            response=client.post(url,json={},headers=self.headers())
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(response.headers['location'],self.receipt['status_url'])
            self.assertEqual(response.headers['retry-after'],'2')
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.previous.side_effect=None
            self.previous.return_value=self.receipt
            replay=client.post(url,json={},headers=self.headers() | {'If-Match':'"run-1"'})
            self.assertEqual(replay.status_code,200,replay.text)
            self.assertTrue(replay.json()['replayed'])
            self.assertNotIn('retry-after',replay.headers)

    def test_http_delete_has_no_body_and_never_returns_202(self):
        with self.client() as client:
            url=f'/api/v1/refresh-runs/{self.run_id}/warning'
            response=client.delete(url,headers=self.headers())
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['result'],'warning_resolved')
            invalid=client.request('DELETE',url,content=b'{}',headers=self.headers())
            self.assertEqual(invalid.status_code,422,invalid.text)
        self.accept.assert_not_called()

    def test_http_authorizes_before_query_and_body_shape_checks(self):
        with self.client() as client:
            for role in ('viewer','analyst'):
                self.actor=Principal('test_'+role,role,uuid4())
                for method,suffix in (('POST','rerun'),('DELETE','warning')):
                    response=client.request(method,f'/api/v1/refresh-runs/{self.run_id}/{suffix}?force=true',
                        content=b'{"force":true}',headers=self.headers() | {'Content-Type':'application/json'})
                    self.assertEqual(response.status_code,403,response.text)
            response=client.delete(f'/api/v1/refresh-runs/{self.run_id}/warning')
            self.assertEqual(response.status_code,401)
        self.target.assert_not_called()

    def test_openapi_describes_both_request_shapes_and_receipt_responses(self):
        canonical=json.loads((Path(__file__).resolve().parents[2]/'docs/openapi.json').read_text())
        with self.client() as client:
            document=client.get('/openapi.json').json()
        for method,suffix,codes in (('post','rerun',('200','202')),('delete','warning',('200',))):
            route='/refresh-runs/{run_id}/'+suffix
            actual=document['paths']['/api/v1'+route][method]
            expected=canonical['paths'][route][method]
            # Canonical headers are reusable OpenAPI references. Compare their
            # resolved meaning instead of assuming every parameter is inline.
            parameters = [canonical['components']['parameters'][p['$ref'].rsplit('/',1)[1]]
                          if '$ref' in p else p for p in expected['parameters']]
            self.assertEqual({(p['in'],p['name']) for p in actual['parameters']},
                             {(p['in'],p['name']) for p in parameters})
            for code in codes:
                self.assertEqual(actual['responses'][code]['content']['application/json']['schema']['$ref'],
                                 '#/components/schemas/ActionReceipt')
            self.assertEqual('requestBody' in actual, method=='post')
            if method=='post':
                self.assertFalse(actual['requestBody']['content']['application/json']['schema']['additionalProperties'])


class ProjectionConnection:
    """Serve one coherent failed-run snapshot to the real read repositories."""

    def __init__(self):
        from datetime import date
        self.now = datetime.now(UTC)
        self.run = dict(id=uuid4(), run_seq=1, revision=2, status='failed',
            requested_at=self.now, started_at=None, finished_at=self.now,
            trigger_kind='manual', requested_by='test_admin', rerun_of_run_id=None,
            settings_revision=4, policy_snapshot={'workflow_policy':'warnings-v1'},
            requested_start=date(2024,10,2), requested_end=None,
            worker_owner_id=None, lease_until=None, execution_fence=0,
            error_code='dispatch_failed', worker_execution_ref=None)
        self.warning = dict(id=uuid4(), run_id=self.run['id'], version_id=None,
            stage='prepare', code='dispatch_failed', created_at=self.now,
            resolved_at=None, resolution=None, resolved_by=None)
        self.control = dict(holder_run_id=self.run['id'])
        self.settings = dict(setup_completed_at=self.now, schedule_timezone='UTC')
        self.attempts = 3

    def execute(self, sql, params=()):
        """Return source rows selected by the production repositories."""
        if not sql.lstrip().startswith('SELECT'):
            raise AssertionError('Read projections must not mutate state.')
        if 'AS has_steps' in sql:
            self.row = dict(has_steps=False, has_running_steps=False)
        elif 'FROM shared_settings' in sql:
            self.row = self.settings
        elif 'FROM refresh_control' in sql:
            self.row = self.control
        elif 'FROM failure_warnings' in sql:
            self.row = self.warning
        elif 'FROM data_versions' in sql:
            self.row = None
        elif 'FROM job_outbox' in sql:
            self.row = dict(dispatch_attempts=self.attempts)
        elif 'COALESCE(max(' in sql:
            self.row = dict(n=1)
        elif 'FROM refresh_steps' in sql:
            self.row = None
        elif 'FROM refresh_runs' in sql:
            self.row = self.run.copy()
        else:
            raise AssertionError('Unexpected read query: '+sql)
        return self

    def fetchone(self):
        """Return the selected scalar snapshot."""
        return self.row

    def fetchall(self):
        """Represent either a single run page or no retained steps."""
        return [self.row] if self.row is not None else []


class RecoveryProjectionTests(unittest.TestCase):
    """The three Admin surfaces must derive recovery flags from the same rule."""

    def setUp(self):
        self.connection = ProjectionConnection()
        self.actor = Principal('test_admin','admin',uuid4())
        self.database = SimpleNamespace(transaction=self.transaction)
        patcher = patch('trinity.auth.repository.resolve_session',return_value=self.actor)
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextmanager
    def transaction(self, *args, **kwargs):
        """Allow only the read-only transaction paths used by these surfaces."""
        if not kwargs.get('readonly'):
            raise AssertionError('Expected a read-only transaction.')
        yield self.connection

    def flags(self):
        """Run app entry, history and detail through production read assembly."""
        from trinity.auth.service import AuthService
        from test_preview_unit import codec
        refresh = RefreshService(self.database, codec_factory=codec)
        with patch('trinity.auth.service.read_publication',return_value=None):
            me = AuthService(self.database).me(self.actor,self.connection)
        history = refresh.history('t'*43)
        detail = refresh.detail('t'*43,str(self.connection.run['id']))
        return [{a.action:a.enabled for a in actions if a.action in ('rerun','delete_warning')}
                for actions in (me.admin_context.actions,history.actions,detail.actions)]

    def test_all_surfaces_enable_only_proven_failure(self):
        self.assertEqual(self.flags(),[dict(rerun=True,delete_warning=True)]*3)
        self.connection.attempts=2
        self.assertEqual(self.flags(),[dict(rerun=False,delete_warning=False)]*3)

    def test_setup_changes_rerun_only_on_all_surfaces(self):
        self.connection.settings['setup_completed_at']=None
        self.assertEqual(self.flags(),[dict(rerun=False,delete_warning=True)]*3)

    def test_historical_run_cannot_inherit_current_holder_actions(self):
        from trinity.refresh.repository import read_context
        run=self.connection.run.copy() | {'id':uuid4()}
        state=read_context(self.connection)
        context=admin_context(self.connection.settings,*state)
        detail=run_view((run,None,None,None,None,None),[],None,context)
        self.assertFalse(any(a.enabled for a in detail.actions if a.action in ('rerun','delete_warning')))
