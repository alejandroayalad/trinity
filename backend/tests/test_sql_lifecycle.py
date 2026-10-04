"""Exercise supervisor failure ordering with explicit lifecycle doubles."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from trinity.errors import Problem
from trinity.queries.client import QueryExecution
from trinity.queries.service import QueryDeadline


class Database:
    @contextmanager
    def transaction(self,*args,**kwargs):yield object()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.docker=Mock(daemon_id='daemon')
        self.reservation={'request_id':uuid4(),'deployment_id':uuid4(),'daemon_id':'daemon',
                          'owner_token':uuid4(),'generation':1,'state':'creating','container_id':None,
                          'container_name':'trinity-query-synthetic'}
        self.execution=QueryExecution(Database(),self.docker,None,self.root,self.reservation['deployment_id'])

    def test_ambiguous_create_retains_capacity_when_name_is_absent(self):
        self.docker.inspect.return_value=None
        with patch('trinity.queries.client.repository.release_removed') as release:
            with self.assertRaises(Problem):self.execution.cleanup(self.reservation,'query_timeout')
            release.assert_not_called()
        self.docker.remove_stopped.assert_not_called()

    def test_known_container_must_be_removed_before_release(self):
        self.reservation.update(state='running',container_id='a'*64)
        events=[]
        def transition(c,r,expected,state,**kwargs):
            events.append(state);return {**r,'state':state}
        self.docker.remove_stopped.side_effect=lambda *a:events.append('removed')
        with patch('trinity.queries.client.repository.transition',side_effect=transition),patch(
                'trinity.queries.client.repository.release_removed',side_effect=lambda *a:events.append('released') or True):
            self.execution.cleanup(self.reservation,'query_timeout')
        self.assertEqual(events,['stopping','removed','cleaning','released'])

    def test_daemon_or_cleanup_failure_never_releases(self):
        self.reservation.update(state='running',container_id='a'*64)
        self.docker.remove_stopped.side_effect=Problem(503,'dependency_unavailable')
        with patch('trinity.queries.client.repository.transition',return_value=self.reservation),patch(
                'trinity.queries.client.repository.release_removed') as release:
            with self.assertRaises(Problem):self.execution.cleanup(self.reservation,'query_timeout')
            release.assert_not_called()

    def test_recovery_on_another_daemon_cannot_clean_up(self):
        self.reservation['daemon_id']='different'
        with patch('trinity.queries.client.repository.claim_expired',return_value=self.reservation):
            with self.assertRaises(Problem):self.execution.recover_one()
        self.docker.inspect.assert_not_called()

    def test_revoked_owner_cannot_stop_new_owner_work(self):
        self.reservation.update(state='running',container_id='a'*64)
        with patch('trinity.queries.client.repository.transition',side_effect=Problem(503,'dependency_unavailable')):
            with self.assertRaises(Problem):self.execution.cleanup(self.reservation,'query_timeout')
        self.docker.remove_stopped.assert_not_called()
