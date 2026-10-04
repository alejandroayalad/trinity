"""Check operator failures and secret-safe output using synthetic HTTP responses."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from trinity.auth.check import check_persona, main
from trinity.auth.preview_check import PreviewFixture, PreviewNotReady, load_preview_fixture
from trinity.queries.preview import PUBLIC_DATASETS
from trinity.queries.preview_schemas import PreviewRange
from test_preview_unit import page, publication, request, wire_rows


def fixture():
    return PreviewFixture(publication=publication(), range=PreviewRange(start='2026-09-03', end='2026-10-02'),
                          facility='01', generator='1',
                          rows={public:wire_rows(internal,2) for public,internal in PUBLIC_DATASETS.items()},
                          diagnostics={public:[] for public in PUBLIC_DATASETS})


class PreviewCheckTests(unittest.TestCase):
    def run_check(self, role='viewer', change=None, enabled=True):
        calls=[]; revoked=False
        def handle(req):
            nonlocal revoked
            calls.append(req)
            path=req.url.path
            if path.endswith('/login'):return httpx.Response(200,json={'access_token':'synthetic-token'})
            if path.endswith('/logout'):
                revoked=True
                return httpx.Response(204)
            if revoked:return httpx.Response(401)
            if path.endswith('/me'):return httpx.Response(200,json={'role':role,'landing_screen':'explore'})
            if path.endswith('/settings'):return httpx.Response(200 if role=='admin' else 403)
            public=path.split('/')[-2]; internal=PUBLIC_DATASETS[public]
            headers={'cache-control':'no-store','x-request-id':'test'}
            if role=='viewer' and internal!='national':
                return httpx.Response(404,json={'code':'dataset_not_found'},headers=headers)
            second='cursor' in req.url.params
            body=page(request(internal,limit=1),wire_rows(internal,2) if not second else wire_rows(internal,2)[1:]).model_dump(mode='json')
            response=httpx.Response(200,json=body,headers=headers)
            return change(response,second) if change else response
        with httpx.Client(transport=httpx.MockTransport(handle),base_url='http://test') as client:
            try:
                result=check_persona(client,role,'synthetic-password',preview=fixture() if enabled else None)
                return result,calls
            finally:
                self.assertTrue(revoked,'Every logged-in failure must attempt logout')

    def test_all_roles_pages_filters_and_revocation(self):
        for role in ('viewer','analyst','admin'):
            with self.subTest(role=role):
                result,calls=self.run_check(role)
                self.assertEqual(result,'explore')
                requests=[r for r in calls if r.url.path.endswith('/preview') and r.url.params]
                self.assertEqual(len(requests),4 if role=='viewer' else 6)
                if role!='viewer':
                    generator=[r for r in requests if 'generator_outages' in r.url.path]
                    self.assertTrue(all(r.url.params['facility']=='01' and r.url.params['generator']=='1' for r in generator))
                self.assertTrue(any('cursor' in r.url.params for r in requests))
                self.assertTrue(calls[-1].url.path.endswith('/preview'))

    def test_default_never_requests_preview(self):
        _,calls=self.run_check(enabled=False)
        self.assertFalse(any(r.url.path.endswith('/preview') for r in calls))

    def test_missing_publication_empty_page_or_continuation_is_not_ready(self):
        def empty(response,second):
            body=response.json();body.update(rows=[],returned_rows=0,next_cursor=None,reason='not_reported')
            return httpx.Response(200,json=body,headers=response.headers)
        def no_cursor(response,second):
            body=response.json();body['next_cursor']=None
            return httpx.Response(200,json=body,headers=response.headers)
        for change in (lambda r,s:httpx.Response(503),empty,no_cursor):
            with self.subTest(change=change),self.assertRaises(PreviewNotReady):self.run_check(change=change)

    def test_wrong_values_publication_diagnostics_and_repeated_page_fail(self):
        for kind in ('value','publication','diagnostics','repeat','headers'):
            def change(response,second):
                body=response.json()
                if kind=='value':body['rows'][0][1]='999.000000'
                elif kind=='publication':body['publication']['publication_event_id']='00000000-0000-4000-8000-000000000099'
                elif kind=='diagnostics':body['diagnostics']=[{'private':'forbidden'}]
                elif kind=='repeat' and second:body['rows']=wire_rows()[0:1]
                return httpx.Response(200,json=body,headers={} if kind=='headers' else response.headers)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_check(change=change)

    def test_fixture_rejects_missing_wrong_filter_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.json'
            for change in (lambda b:b.update(publication=None),lambda b:b.update(facility='wrong'),
                           lambda b:b['rows'].update(national_outages=[wire_rows()[0]]*2)):
                body=fixture().model_dump(mode='json');change(body);path.write_text(json.dumps(body))
                with self.assertRaises(PreviewNotReady):load_preview_fixture(path)
            path.write_text(fixture().model_dump_json())
            self.assertEqual(load_preview_fixture(path),fixture())
            path.write_bytes(b'x'*131073)
            with self.assertRaises(PreviewNotReady):load_preview_fixture(path)

    def test_cli_missing_fixture_reports_incomplete_without_password_prompt(self):
        stderr=io.StringIO()
        with patch('sys.argv',['check','--preview-fixture','/nonexistent/private-fixture.json']), \
                patch('trinity.auth.check.getpass') as prompt,contextlib.redirect_stderr(stderr):
            self.assertEqual(main(),2)
        prompt.assert_not_called()
        self.assertIn('not ready/incomplete',stderr.getvalue())
        self.assertNotIn('private-fixture',stderr.getvalue())

    def test_cli_error_never_prints_sensitive_exception(self):
        stderr=io.StringIO()
        with patch('sys.argv',['check']),patch('sys.stdin.isatty',return_value=True), \
                patch('trinity.auth.check.getpass',return_value='password-canary'), \
                patch('trinity.auth.check.check_persona',side_effect=ValueError('token-cursor-body-canary')), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(main(),1)
        self.assertNotIn('canary',stderr.getvalue())
