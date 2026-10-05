"""Verify choices through real HTTP, PostgreSQL and isolated DataFusion containers."""

import io
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import candidate, publish_fixture, loopback
from preview_runtime_fixture import IMAGE, RuntimeSandbox
from test_choices import choice_codec
from trinity.errors import Problem
from trinity.main import create_app
from trinity.queries.choice_service import ChoiceService
from trinity.queries.service import QueryService


@unittest.skipUnless(DSN and IMAGE, 'Disposable PostgreSQL and matching query image required')
class ChoiceRuntimeTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.report, self.receipt, self.objects = candidate(self.root/'candidate')
        self.event, self.version = publish_fixture(DSN,self.report,self.receipt)
        self.sandbox = RuntimeSandbox(self.database,self.root/'stage'); self.addCleanup(self.sandbox.close)
        self.sandbox.client.add(self.version,self.objects)
        self.choices = ChoiceService(self.database,self.sandbox.execution,codec_factory=choice_codec)
        self.app = create_app(service=self.service,choice_service=self.choices)
        self.token = self.login('analyst')['Authorization'][7:]

    def execute(self, pairs=(), dataset='facility_outages', choice='facilities'):
        return self.choices.execute(self.token,dataset,choice,pairs)

    def assert_clean(self, outcome='succeeded'):
        reservations = self.sql('SELECT state,cleanup_complete,outcome FROM query_reservations ORDER BY created_at')
        self.assertTrue(reservations)
        self.assertTrue(all(row['state']=='released' and row['cleanup_complete'] for row in reservations))
        self.assertEqual(reservations[-1]['outcome'],outcome)
        self.assertEqual(self.sandbox.remaining_containers(),[])
        self.assertEqual(list(self.sandbox.stage.iterdir()),[])

    def expected_facilities(self, dataset):
        # Derive the expected choices independently from stored producer bytes.
        rows = pq.read_table(io.BytesIO(self.objects[f'data/{dataset}.parquet'])).to_pylist()
        result = []
        for facility in sorted({row['facility'] for row in rows}):
            named = [row for row in rows if row['facility']==facility and row['facilityName'] is not None]
            latest = max((row['period'] for row in named),default=None)
            label = min((row['facilityName'] for row in named if row['period']==latest),default=None)
            result.append({'facility':facility,'facilityName':label})
        return result

    def test_loopback_roles_paging_search_and_parent_scoping(self):
        with loopback(self.app) as http:
            for role in ('viewer','analyst','admin'):
                login = http.post('/api/v1/auth/login',json={'username':role,'password':self.passwords[role]})
                self.assertEqual(login.status_code,200)
                headers = {'Authorization':'Bearer '+login.json()['access_token']}
                for dataset in ('facility','generator'):
                    path = f'/api/v1/datasets/{dataset}_outages/facilities'
                    before = len(self.sandbox.client.calls)
                    response = http.get(path,params={'limit':'1'},headers=headers)
                    if role == 'viewer':
                        self.assertEqual(response.status_code,404)
                        self.assertEqual(len(self.sandbox.client.calls),before)
                        continue
                    items = []
                    while True:
                        self.assertEqual(response.status_code,200)
                        body = response.json()
                        self.assertEqual(set(body),{'publication','range','items','next_cursor'})
                        self.assertEqual(response.headers['cache-control'],'no-store')
                        items.extend(body['items'])
                        if body['next_cursor'] is None:
                            break
                        response = http.get(path,params={'limit':'1','cursor':body['next_cursor']},headers=headers)
                    self.assertEqual(items,self.expected_facilities(dataset))
                    search = http.get(path,params={'search':'001a'},headers=headers)
                    self.assertEqual(search.status_code,200)
                    self.assertEqual([item['facility'] for item in search.json()['items']],['001a'])
                path = '/api/v1/datasets/generator_outages/generators'
                response = http.get(path,params={'facility':'001a'},headers=headers)
                self.assertEqual(response.status_code,404 if role=='viewer' else 200)
                if role != 'viewer':
                    self.assertEqual(response.json()['facility'],'001a')
                    self.assertTrue(response.json()['items'])
                    self.assertTrue(all(item['facility']=='001a' for item in response.json()['items']))
                    empty = http.get(path,params={'facility':'missing'},headers=headers)
                    self.assertEqual(empty.status_code,200)
                    self.assertEqual(empty.json()['items'],[])
        self.assert_clean()

    def test_changed_publication_and_revoked_authority_deny_before_storage(self):
        first = self.execute([('limit','1')])
        self.assertIsNotNone(first.next_cursor)
        before = len(self.sandbox.client.calls)
        # Publish a second complete synthetic candidate; old cursors cannot pin it.
        report, receipt, objects = candidate(self.root/'second')
        _, version = publish_fixture(DSN,report,receipt)
        self.sandbox.client.add(version,objects)
        with self.assertRaises(Problem) as caught:
            self.execute([('limit','1'),('cursor',first.next_cursor)])
        self.assertEqual(caught.exception.code,'publication_changed')
        self.sql("UPDATE local_users SET role='viewer' WHERE id='test_analyst'")
        with self.assertRaises(Problem) as caught:
            self.execute()
        self.assertEqual(caught.exception.code,'dataset_not_found')
        self.assertEqual(len(self.sandbox.client.calls),before)
        self.assert_clean()

    def test_shared_sql_rate_counter_and_invalid_inputs(self):
        sql = QueryService(self.database,self.sandbox.execution)
        # SQL semantic failures retain their debit. Choices must see those debits
        # in the same PostgreSQL counter instead of opening a separate quota.
        for _ in range(29):
            with self.assertRaises(Problem) as caught:
                sql.prepare(self.token,'DELETE FROM facility_outages')
            self.assertEqual(caught.exception.code,'sql_not_allowed')
        self.execute()
        with self.assertRaises(Problem) as caught:
            self.execute()
        self.assertEqual(caught.exception.code,'rate_limited')
        self.assert_clean()

    def test_corrupt_published_bytes_never_launch_or_return_partial_choices(self):
        path = next(key for key in self.sandbox.client.objects if key.endswith('data/facility.parquet'))
        self.sandbox.client.objects[path] = b'corrupt'
        with self.assertRaises(Problem) as caught:
            self.execute()
        self.assertEqual(caught.exception.code,'dependency_unavailable')
        self.assertEqual(self.sandbox.created,[])
        self.assert_clean('dependency_unavailable')

    def test_empty_publication_and_invalid_http_inputs_do_not_stage(self):
        with loopback(self.app) as http:
            headers = {'Authorization':'Bearer '+self.token}
            path = '/api/v1/datasets/generator_outages/generators'
            for query in ('?facility=001a&facility=001b','?facility=001a&search=x','?limit=101',''):
                self.assertEqual(http.get(path+query,headers=headers).status_code,422)
            self.sql('UPDATE active_publication SET publication_event_id=NULL')
            response = http.get(path,params={'facility':'001a'},headers=headers)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['code'],'data_unavailable')
        self.assertEqual(self.sandbox.client.calls,[])
        self.assertEqual(self.sandbox.created,[])
