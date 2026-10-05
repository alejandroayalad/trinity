"""Prove actual query containers consume real publication effects and pinned files."""
import unittest
from fastapi.testclient import TestClient
from postgres_fixture import DSN
from publication_fixture import PublicationFixture
from preview_runtime_fixture import IMAGE, RuntimeSandbox
from test_preview_unit import codec
from trinity.main import create_app
from trinity.queries.service import PreviewService, QueryService
from trinity.errors import Problem

@unittest.skipUnless(DSN and IMAGE,'Disposable PostgreSQL and query image required')
class PublicationRuntimeTests(PublicationFixture,unittest.TestCase):
    def test_published_readers_roles_inflight_pinning_and_cursor_switch(self):
        # No fixture inserts an event or active pointer. Both versions are
        # activated by the production worker over real registered evidence.
        first=self.worker.execute(self.payload())
        sandbox=RuntimeSandbox(self.database,self.root/'stage');self.addCleanup(sandbox.close)
        sandbox.client.add(self.version,self.objects)
        previews=PreviewService(self.database,sandbox.execution,codec_factory=codec)
        queries=QueryService(self.database,sandbox.execution)
        app=create_app(service=self.service,preview_service=previews,query_service=queries)
        with TestClient(app) as client:
            for role in ('viewer','analyst','admin'):
                token=self.login(role)
                catalog=client.get('/api/v1/catalog',headers=token)
                self.assertEqual(catalog.status_code,200,catalog.text)
                self.assertEqual(catalog.json()['publication']['publication_event_id'],str(first['id']))
                for dataset in ('national','facility','generator'):
                    page=client.get(f'/api/v1/datasets/{dataset}_outages/preview',headers=token,params={'limit':'1'})
                    self.assertEqual(page.status_code,404 if role=='viewer' and dataset!='national' else 200,page.text)
                sql=client.post('/api/v1/queries',headers=token,json={'sql':'SELECT COUNT(*) FROM national_outages'})
                self.assertEqual(sql.status_code,403 if role=='viewer' else 200,sql.text)
        token=self.admin['Authorization'][7:]
        old_page=previews.execute(token,'national_outages',[('limit','1')])
        self.assertIsNotNone(old_page.next_cursor)
        old_version=self.version
        preview_prepared,preview_execution=previews.prepare(token,'national_outages',[('limit','1')])
        prepared,execution=queries.prepare(token,'SELECT COUNT(*) FROM national_outages')
        self.new_candidate(warnings=True)
        approved=self.command('approve');self.assertEqual(approved.status_code,202,approved.text)
        second=self.worker.execute(self.payload());sandbox.client.add(self.version,self.objects)
        # Execute after the switch: the already-admitted request still uses A.
        pinned=execution.execute(prepared)
        self.assertEqual(pinned.publication.publication_event_id,first['id'])
        sandbox.client.calls.clear()
        pinned_preview=preview_execution.execute(preview_prepared)
        self.assertEqual(pinned_preview.publication,old_page.publication)
        self.assertEqual(pinned_preview.diagnostics,old_page.diagnostics)
        self.assertEqual(pinned_preview.rows,old_page.rows)
        self.assertTrue(sandbox.client.calls)
        self.assertTrue(all(key.startswith(f'versions/{old_version}/') for key in sandbox.client.calls))
        new_page=previews.execute(token,'national_outages',[('limit','1')])
        self.assertEqual(new_page.publication.publication_event_id,second['id'])
        with self.assertRaises(Problem) as failure:
            previews.execute(token,'national_outages',[('limit','1'),('cursor',old_page.next_cursor)])
        self.assertEqual(failure.exception.code,'publication_changed')
        self.assertTrue(new_page.diagnostics)
        self.assertEqual(queries.execute(token,'SELECT COUNT(*) FROM national_outages').publication.publication_event_id,second['id'])
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/catalog',headers=self.admin).json()['publication']['publication_event_id'],str(second['id']))
        self.assertEqual(sandbox.remaining_containers(),[])
