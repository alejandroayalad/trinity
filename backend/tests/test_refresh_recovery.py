"""Check recovery syntax and retained evidence without runtime-stop claims."""
from copy import deepcopy
from datetime import UTC, datetime
import unittest
from uuid import uuid4

from trinity.errors import Problem
from trinity.refresh.recovery import recovery_actions
from trinity.refresh.schemas import ActionReceipt, parse_recovery_command


class ParsingTests(unittest.TestCase):
    """Reject ambiguous command identity before any future state lookup."""

    def setUp(self):
        self.values = dict(run_id=str(uuid4()), action='rerun', raw=b'{}',
                           key_headers=[str(uuid4())], etags=['"run-12"'], pairs=())

    def parse(self, **changes):
        """Keep valid HTTP fields fixed except the requested variation."""
        return parse_recovery_command(**(self.values | changes))

    def error(self, status, code='invalid_request', **changes):
        """Assert only safe public error fields."""
        with self.assertRaises(Problem) as caught:
            self.parse(**changes)
        self.assertEqual((caught.exception.status, caught.exception.code), (status, code))

    def test_rerun_retains_identity_and_old_revision_for_replay(self):
        value = self.parse(etags=['"run-0"'])
        self.assertEqual((str(value.run_id), str(value.key), value.action, value.revision),
                         (self.values['run_id'], self.values['key_headers'][0], 'rerun', '0'))

    def test_delete_requires_zero_bytes(self):
        self.assertEqual(self.parse(action='delete_warning', raw=b'').action, 'delete_warning')
        for raw in (b'{}', b' ', b'null', b'[]', b'\n'):
            with self.subTest(raw=raw):
                self.error(422, action='delete_warning', raw=raw)

    def test_rerun_requires_object_without_fields(self):
        for raw in (b'null', b'[]', b'false', b'1', b'{"actor_id":"admin"}'):
            with self.subTest(raw=raw):
                self.error(422, raw=raw)

    def test_invalid_json_is_distinct_from_wrong_shape(self):
        for raw in (b'', b'{', b'\xff'):
            with self.subTest(raw=raw):
                self.error(400, 'invalid_json', raw=raw)

    def test_missing_precondition_precedes_body_validation(self):
        self.error(428, 'precondition_required', etags=[], raw=b'bad')

    def test_only_single_strong_run_tag_is_valid(self):
        for tag in ('*', '"candidate-12"', '"run-01"', '"run--1"', 'W/"run-12"',
                    'run-12', '"run-12","run-13"', '"run-1.0"', '"run-12"\n'):
            with self.subTest(tag=tag):
                self.error(422, etags=[tag])
        self.error(422, etags=['"run-12"', '"run-12"'])

    def test_missing_or_repeated_key_is_rejected(self):
        self.error(422, 'idempotency_key_required', key_headers=[])
        key = self.values['key_headers'][0]
        self.error(422, key_headers=[key, key])
        self.error(422, key_headers=[key + ',' + key])

    def test_uuid_shapes_queries_and_actions_are_strict(self):
        for action, raw in (('rerun', b'{}'), ('delete_warning', b'')):
            for value in ('bad', self.values['run_id'].replace('-', ''), '{'+self.values['run_id']+'}'):
                with self.subTest(action=action, value=value):
                    self.error(422, action=action, raw=raw, run_id=value)
                    self.error(422, action=action, raw=raw, key_headers=[value])
            self.error(422, action=action, raw=raw, pairs=[('force', 'true')])
        self.error(422, action='discard', raw=b'')

    def test_receipt_accepts_new_and_existing_action_values(self):
        fields = dict(operation_id=uuid4(), accepted_at=datetime.now(UTC), run_id=uuid4(),
                      version_id=None, status_url='/api/v1/refresh-runs/'+self.values['run_id'], replayed=False)
        for action, result in (('rerun','queued'), ('delete_warning','warning_resolved'),
                               ('start_refresh','queued'), ('approve','queued'),
                               ('publication_retry','queued'), ('discard','discarded')):
            with self.subTest(action=action):
                self.assertEqual(ActionReceipt(**fields, action=action, result=result).result, result)


class EvidenceConnection:
    """Supply named SELECT results; fail if eligibility tries to write."""

    def __init__(self):
        self.event = None
        self.steps = dict(has_steps=True, has_running_steps=False)
        self.outbox = dict(dispatch_attempts=3)
        self.publication_step = None
        self.queries = []

    def execute(self, sql, params):
        """Select fixture evidence by object rather than call order."""
        self.queries.append((sql, params))
        if not sql.lstrip().startswith('SELECT'):
            raise AssertionError('Eligibility must be read-only.')
        if 'publication_events' in sql:
            self.row = self.event
        elif 'AS has_steps' in sql:
            self.row = self.steps
        elif 'job_outbox' in sql:
            self.row = self.outbox
        elif "work_key='publication'" in sql:
            self.row = self.publication_step
        else:
            raise AssertionError('Unexpected evidence query.')
        return self

    def fetchone(self):
        """Return the explicit fixture row, never implicit success."""
        return self.row


class EligibilityTests(unittest.TestCase):
    """Model producer rows; these fixtures do not prove a real child stopped."""

    def setUp(self):
        self.now = datetime.now(UTC)
        run_id, version_id, owner = uuid4(), uuid4(), uuid4()
        self.db = EvidenceConnection()
        self.settings = dict(setup_completed_at=self.now)
        self.control = dict(holder_run_id=run_id)
        self.run = dict(id=run_id, status='failed', started_at=self.now, finished_at=self.now,
                        worker_owner_id=owner, lease_until=None, execution_fence=2,
                        error_code='refresh_failed', publication_generation=0,
                        worker_execution_ref=dict(owner=str(owner), child_stopped=True))
        self.version = dict(id=version_id, run_id=run_id, disposition='active', status='rejected')
        self.warning = dict(run_id=run_id, version_id=version_id, code='refresh_failed', stage='prepare',
                            resolved_at=None, resolution=None, resolved_by=None)

    def actions(self):
        """Evaluate fixture evidence through the common public helper."""
        return recovery_actions(self.db, self.settings, self.control, self.run, self.version, self.warning)

    def denied(self):
        """Unknown evidence must disable both actions."""
        self.assertEqual(self.actions(), dict(rerun=False, delete_warning=False))

    def preclaim(self, code='dispatch_failed'):
        """Model queue exhaustion or policy rejection before any owner starts."""
        self.run.update(started_at=None, worker_owner_id=None, execution_fence=0,
                        worker_execution_ref=None, error_code=code)
        self.version = None
        self.warning.update(version_id=None, code=code, stage='prepare' if code=='dispatch_failed' else 'extract')
        self.db.steps = dict(has_steps=False, has_running_steps=False)

    def publication(self):
        """Model the current generation's finished publication failure."""
        self.run.update(status='publication_failed', finished_at=None, worker_owner_id=None,
                        error_code='publication_deadline', publication_generation=4)
        self.version['status'] = 'validated'
        self.warning.update(stage='publish', code='publication_deadline')
        self.db.publication_step = dict(status='failed', finished_at=self.now, error_code='publication_deadline')

    def test_confirmed_stop_keeps_owner_and_preserves_inputs(self):
        before = deepcopy((self.run, self.version, self.warning, self.control))
        self.assertEqual(self.actions(), dict(rerun=True, delete_warning=True))
        self.assertEqual(before, (self.run, self.version, self.warning, self.control))

    def test_setup_only_gates_new_run(self):
        self.settings['setup_completed_at'] = None
        self.assertEqual(self.actions(), dict(rerun=False, delete_warning=True))

    def test_discovery_failure_without_candidate(self):
        self.version = None
        self.warning.update(version_id=None, stage='extract')
        self.assertTrue(self.actions()['rerun'])

    def test_recorded_candidate_identity_cannot_point_to_other_work(self):
        # Freeze can fail before version_id is added to the reference. Once
        # present, however, that identity must match the retained candidate.
        self.run['worker_execution_ref']['version_id'] = str(self.version['id'])
        self.assertTrue(self.actions()['rerun'])
        self.run['worker_execution_ref']['version_id'] = str(uuid4())
        self.denied()
        self.version = None
        self.warning['version_id'] = None
        self.denied()

    def test_reclaimed_owner_must_match_stop_record(self):
        self.run['error_code'] = self.warning['code'] = 'worker_lost'
        new_owner = uuid4()
        self.run.update(worker_owner_id=new_owner, execution_fence=3)
        self.denied()
        self.run['worker_execution_ref']['owner'] = str(new_owner)
        self.assertTrue(self.actions()['rerun'])

    def test_missing_false_or_wrong_owner_stop_evidence_is_rejected(self):
        for ref in (None, {}, dict(child_stopped=False), dict(child_stopped=1),
                    dict(child_stopped=True, owner=str(uuid4()))):
            with self.subTest(ref=ref):
                self.run['worker_execution_ref'] = ref
                self.denied()

    def test_expired_nonnull_lease_is_not_stop_proof(self):
        self.run['lease_until'] = datetime(2000, 1, 1, tzinfo=UTC)
        self.denied()

    def test_incomplete_failure_or_running_step_is_rejected(self):
        self.run['finished_at'] = None
        self.denied()
        self.run['finished_at'] = self.now
        self.db.steps['has_running_steps'] = True
        self.denied()

    def test_started_failure_needs_owner_fence_and_rejected_candidate(self):
        for field, value in (('worker_owner_id',None), ('execution_fence',0), ('error_code','unknown')):
            original = self.run[field]
            self.run[field] = value
            self.denied()
            self.run[field] = original
        self.version['status'] = 'validated'
        self.denied()

    def test_active_or_terminal_nonfailure_states_reject_before_evidence_reads(self):
        for status in ('requested','running','awaiting_approval','publishing','succeeded','discarded','superseded'):
            self.run['status'] = status
            self.denied()
        self.assertEqual(self.db.queries, [])
        self.run['status'] = 'failed'
        self.control['holder_run_id'] = uuid4()
        self.denied()
        self.assertEqual(self.db.queries, [])

    def test_warning_identity_and_resolution_must_match(self):
        for field, value in (('resolved_at',self.now), ('resolution','rerun'), ('resolved_by','admin'),
                             ('run_id',uuid4()), ('version_id',uuid4()), ('code','other')):
            original = self.warning[field]
            self.warning[field] = value
            self.denied()
            self.warning[field] = original
        self.assertEqual(self.db.queries, [])

    def test_missing_context_keeps_actions_disabled(self):
        for field in ('run','control','warning'):
            original = getattr(self, field)
            setattr(self, field, None)
            self.denied()
            setattr(self, field, original)

    def test_discarded_wrong_run_and_published_candidates_are_protected(self):
        for state in ('discarded','superseded'):
            self.version['disposition'] = state
            self.denied()
        self.version['disposition'] = 'active'
        self.version['run_id'] = uuid4()
        self.denied()
        self.version['run_id'] = self.run['id']
        self.db.event = dict(id=uuid4())
        self.denied()

    def test_dispatch_exhaustion_requires_recorded_attempts(self):
        self.preclaim()
        self.assertTrue(self.actions()['rerun'])
        self.db.outbox['dispatch_attempts'] = 2
        self.denied()

    def test_preclaim_policy_rejection_requires_dispatch(self):
        self.preclaim('refresh_failed')
        self.db.outbox['dispatch_attempts'] = 1
        self.assertTrue(self.actions()['rerun'])
        self.db.outbox['dispatch_attempts'] = 0
        self.denied()

    def test_preclaim_rejects_execution_trace_or_missing_outbox(self):
        for field, value in (('worker_owner_id',uuid4()), ('execution_fence',1),
                             ('worker_execution_ref',dict(child_stopped=True))):
            self.preclaim()
            self.run[field] = value
            self.denied()
        self.preclaim()
        self.db.steps['has_steps'] = True
        self.denied()
        self.preclaim()
        self.db.outbox = None
        self.denied()

    def test_publication_requires_current_generation_failure_step(self):
        self.publication()
        self.assertTrue(self.actions()['rerun'])
        self.assertEqual(self.db.queries[-1][1], (self.run['id'],5))
        self.db.publication_step = None
        self.denied()

    def test_publication_rejects_incomplete_stop_and_retained_owner(self):
        for change in (dict(status='running'), dict(finished_at=None), dict(error_code=None)):
            self.publication()
            self.db.publication_step.update(change)
            self.denied()
        self.publication()
        self.run['worker_owner_id'] = uuid4()
        self.denied()

    def test_publication_requires_candidate_and_publish_warning(self):
        self.publication()
        self.warning['stage'] = 'prepare'
        self.denied()
        self.publication()
        self.version = None
        self.warning['version_id'] = None
        self.denied()

    def test_database_failure_propagates_to_service_wrapper(self):
        def unavailable(*args):
            raise RuntimeError('synthetic unavailable database')
        self.db.execute = unavailable
        with self.assertRaises(RuntimeError):
            self.actions()


if __name__ == '__main__':
    unittest.main()
