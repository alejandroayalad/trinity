"""Exercise shared cleanup for preview with fake lifecycle transports."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import Mock, patch
import unittest
from uuid import uuid4

from trinity.contracts.queries import BINDING_FIELDS, canonical_message, request_message
from trinity.errors import Problem
from trinity.queries.client import QueryExecution
from trinity.queries.service import PreparedPreview, QueryDeadline
from trinity.queries.staging import stage_query, PublishedReader
from trinity.queries.runtime.__main__ import run_request
from test_preview_engine import operation
from test_preview_unit import codec
from test_preview_provenance import frozen_fixture
from test_preview_service import Database
from test_sql_staging import bundle, Client
from types import SimpleNamespace


class PreviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pinned, _ = frozen_fixture()
        self.reservation = dict(request_id=uuid4(),deployment_id=uuid4(),daemon_id='synthetic',
                                owner_token=uuid4(),generation=1,state='reserved',container_id=None,
                                container_name='trinity-query-synthetic')
        self.docker = Mock(daemon_id='synthetic')
        self.docker.create.return_value = 'a'*64
        self.docker.inspect.return_value = {'State': {'Running':False,'ExitCode':0,'OOMKilled':False}}
        self.attached = Mock()
        self.docker.attach.return_value = self.attached, iter(())
        self.execution = QueryExecution(Database(), self.docker, Mock(), self.root,self.reservation['deployment_id'])
        self.prepared = PreparedPreview(operation(),self.pinned,self.reservation,QueryDeadline(30),0,codec())
        self.events = []
        def change(reservation, expected, state, **kwargs):
            self.events.append(state)
            return reservation | {'state':state} | kwargs
        self.execution.change = change
        message = request_message(self.reservation['request_id'],self.pinned.publication.version_id,self.prepared.query)
        from trinity.catalog.registry import describe_dataset
        result = {'columns':[c.model_dump() for c in describe_dataset('national').columns],
                  'rows':[['2025-01-01','100.000000','1.000000',None],
                          ['2025-01-02','100.000000','2.000000',None]],'has_more':True}
        self.response = {key:message[key] for key in BINDING_FIELDS} | {'result':result}
        patches = {'stage_query':Mock(), 'read_preview_diagnostics':Mock(return_value=[]),
                   'read_frames':Mock(side_effect=lambda *a:canonical_message(self.response)),
                   'repository.release_removed':Mock(side_effect=lambda *a:self.events.append('released') or True)}
        self.mocks = patches
        for target, mock in patches.items():
            handle = patch('trinity.queries.client.'+target,mock)
            handle.start();self.addCleanup(handle.stop)
        self.docker.remove_stopped.side_effect = lambda *a:self.events.append('removed')

    def test_success_signs_only_after_bound_output_and_returns_after_cleanup(self):
        response = self.execution.execute(self.prepared)
        self.assertEqual(codec().decode(response.next_cursor).after,('2025-01-02',))
        self.assertEqual(self.events[-4:],['stopping','removed','cleaning','released'])
        self.attached.close.assert_called_once()
        self.docker.client.close.assert_called_once()

    def test_bad_result_and_signing_failure_still_confirm_removal_before_release(self):
        self.response['operation_kind'] = 'sql'
        with self.assertRaises(Problem):
            self.execution.execute(self.prepared)
        self.assertEqual(self.events[-4:],['stopping','removed','cleaning','released'])
        self.response['operation_kind'] = 'preview'
        bad_codec = Mock()
        bad_codec.encode.side_effect = Problem(503,'dependency_unavailable')
        with self.assertRaises(Problem):
            self.execution.execute(replace(self.prepared,codec=bad_codec))
        self.assertEqual(self.events[-4:],['stopping','removed','cleaning','released'])

    def test_attach_close_failure_still_attempts_owned_cleanup(self):
        self.attached.close.side_effect = RuntimeError('synthetic close failure')
        with self.assertRaises(RuntimeError):
            self.execution.execute(self.prepared)
        self.assertEqual(self.events[-4:],['stopping','removed','cleaning','released'])
        self.docker.client.close.assert_called_once()

    def test_unknown_termination_never_releases_capacity(self):
        self.docker.remove_stopped.side_effect = Problem(503,'dependency_unavailable')
        with self.assertRaises(Problem):
            self.execution.execute(self.prepared)
        self.mocks['repository.release_removed'].assert_not_called()
        self.assertNotIn('released',self.events)

    def test_provenance_failure_never_stages_or_starts_container(self):
        self.mocks['read_preview_diagnostics'].side_effect = Problem(503,'dependency_unavailable')
        self.execution.cleanup = Mock()
        with self.assertRaises(Problem):
            self.execution.execute(self.prepared)
        self.mocks['stage_query'].assert_not_called()
        self.docker.create.assert_not_called()
        self.execution.cleanup.assert_called_once()
        self.assertEqual(self.execution.cleanup.call_args.args[0]['state'],'staging')

    def test_staging_timeout_and_ambiguous_create_use_shared_failure_cleanup(self):
        self.mocks['stage_query'].side_effect = Problem(504,'query_timeout')
        self.execution.cleanup = Mock()
        with self.assertRaises(Problem):
            self.execution.execute(self.prepared)
        self.docker.create.assert_not_called()
        self.assertEqual(self.execution.cleanup.call_args.args[1],'query_timeout')
        self.mocks['stage_query'].side_effect = None
        self.docker.create.side_effect = Problem(503,'dependency_unavailable')
        with self.assertRaises(Problem):
            self.execution.execute(self.prepared)
        self.assertEqual(self.execution.cleanup.call_args.args[0]['state'],'creating')
        self.docker.start.assert_not_called()

    def test_expired_execution_or_oom_returns_no_page(self):
        for deadline, oom in ((QueryDeadline(-1),False),(QueryDeadline(30),True)):
            self.docker.inspect.return_value['State']['OOMKilled'] = oom
            with self.assertRaises(Problem) as caught:
                self.execution.execute(replace(self.prepared,deadline=deadline))
            self.assertEqual(caught.exception.code,'query_resource_limit' if oom else 'query_timeout')
            self.assertEqual(self.events[-4:],['stopping','removed','cleaning','released'])


    def test_disconnect_while_container_runs_ends_it_and_releases_capacity(self):
        # supervised_call sets this event when the browser aborts its request.
        # The event is set from inside inspect() so the container is already
        # running when the cancel arrives. The next poll must stop the wait.
        cancelled = threading.Event()
        deadline = QueryDeadline(30)
        deadline.cancelled = cancelled
        def running(_identifier):
            cancelled.set()
            return {'State': {'Running': True, 'ExitCode': 0, 'OOMKilled': False}}
        self.docker.inspect.side_effect = running
        with self.assertRaises(Problem) as caught:
            self.execution.execute(replace(self.prepared, deadline=deadline))
        self.assertEqual((caught.exception.status, caught.exception.code), (504, 'query_timeout'))
        # Cleanup removes the container before it releases the slot.
        self.docker.remove_stopped.assert_called_once()
        self.assertEqual(self.events[-4:], ['stopping', 'removed', 'cleaning', 'released'])
        self.attached.close.assert_called_once()


class PreviewStagingTests(unittest.TestCase):
    def test_selected_dataset_only_and_producer_runtime_protocol_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pinned, objects = bundle(root/'source')
            stage = root/'stage';stage.mkdir()
            client = Client(objects)
            reader = PublishedReader(client,SimpleNamespace(bucket='synthetic',prefix='versions'))
            op = operation('generator',version_id=str(pinned.publication.version_id),
                           publication_event_id=str(pinned.publication.publication_event_id))
            staged = stage_query(stage,uuid4(),pinned,op,reader,QueryDeadline(30))
            response = run_request((staged.directory/'request.json').read_bytes(),staged.directory/'data')
            self.assertEqual(response['operation_kind'],'preview')
            self.assertEqual(len(response['result']['rows']),2)
            self.assertTrue(response['result']['has_more'])
            self.assertEqual(len(client.calls),2)
            self.assertFalse(any('national' in key or 'facility' in key for key in client.calls))
            self.assertEqual(sorted(p.name for p in staged.directory.iterdir()),['data','request.json'])
            staged.cleanup()
