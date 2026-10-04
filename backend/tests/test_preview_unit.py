"""Exercise preview contracts offline; no publication, database or engine is used."""

import base64
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import hmac
import json
import os
import subprocess
import sys
from types import MappingProxyType
import unittest
from unittest.mock import patch
from uuid import UUID

from pydantic import SecretBytes, ValidationError

from trinity.auth.permissions import Principal
from trinity.auth.schemas import Publication
from trinity.catalog.registry import describe_dataset
from trinity.connector.validate import MESSAGES
from trinity.errors import Problem
from trinity.queries.cursors import CursorCodec, CursorKeys, load_cursor_keys, resolve_continuation
from trinity.queries.preview import (
    PreviewInput, ResolvedPreview, authorize_preview, key_order, parse_preview_input,
    resolve_preview, validate_filters, validate_key,
)
from trinity.queries.preview_schemas import (
    MAX_RESPONSE_BYTES, PreviewDiagnostic, PreviewRange, PreviewResponse,
    build_preview_response, serialize_preview_rows,
)

PUBLICATION_ID = UUID('00000000-0000-4000-8000-000000000001')
VERSION_ID = UUID('00000000-0000-4000-8000-000000000002')
# Synthetic public test vectors only; never use these bytes for a deployed key.
KEY = bytes(range(32))
OTHER_KEY = bytes(range(32, 64))


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def environment(active='a', keys=None):
    return {'TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID': active,
            'TRINITY_PREVIEW_CURSOR_KEYS_JSON': json.dumps({k: encoded(v) for k, v in (keys or {'a': KEY}).items()})}


def codec():
    return CursorCodec(load_cursor_keys(environment()))


def publication(**changes):
    values = dict(publication_event_id=PUBLICATION_ID, version_id=VERSION_ID,
                  published_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
                  coverage_start=date(2024, 1, 1), coverage_end=date(2026, 10, 2),
                  latest_observation_date=date(2026, 10, 2))
    values.update(changes)
    return Publication(**values)


def request(dataset='national', **changes):
    values = dict(dataset=dataset, start=date(2026, 9, 3), end=date(2026, 10, 2))
    values.update(changes)
    return ResolvedPreview(**values)


def native_row(dataset='national', period=date(2026, 9, 3), facility='01', generator='1', **values):
    row = {'period': period, 'facility': facility, 'generator': generator, 'facilityName': 'Plant',
           'capacity': Decimal('100.000001'), 'outage': Decimal('-0.000001'), 'percentOutage': None}
    row.update(values)
    return [row[c.name] for c in describe_dataset(dataset).columns]


def wire_rows(dataset='national', count=1):
    return serialize_preview_rows(dataset, [native_row(dataset, date(2026, 9, 3+i)) for i in range(count)])


def page(req=None, rows=None, **changes):
    return build_preview_response(req or request(), publication(), wire_rows() if rows is None else rows,
                                  diagnostics=changes.pop('diagnostics', []), codec=changes.pop('codec', codec()),
                                  **changes)


class SafeAssertions(unittest.TestCase):
    def problem(self, code, function, *args, status=None, **kwargs):
        with self.assertRaises(Problem) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)
        if status is not None:
            self.assertEqual(raised.exception.status, status)
        self.assertEqual(str(raised.exception), code)
        return raised.exception


class PreviewInputTests(SafeAssertions):
    def test_role_and_public_name_matrix(self):
        for role in ('viewer', 'analyst', 'admin'):
            actor = Principal('test-user', role, 'session')
            for dataset in ('national', 'facility', 'generator'):
                name = dataset + '_outages'
                if role == 'viewer' and dataset != 'national':
                    self.problem('dataset_not_found', authorize_preview, actor, name, status=404)
                else:
                    self.assertEqual(authorize_preview(actor, name), dataset)
            for name in ('national', 'unknown', 'National_outages', None, []):
                self.problem('dataset_not_found', authorize_preview, actor, name, status=404)
        self.problem('forbidden', authorize_preview, Principal('x', 'unknown', 's'), 'national_outages')

    def test_primitive_parser_preserves_values_without_second_decode(self):
        data = parse_preview_input([('facility', ' 01+%2F '), ('generator', "1' OR 1=1 --"), ('limit', '1000')])
        self.assertEqual(data.facility, ' 01+%2F ')
        self.assertEqual(data.generator, "1' OR 1=1 --")
        self.assertEqual(data.limit, 1000)
        self.assertIsNone(data.start)
        self.assertEqual(parse_preview_input([]).limit, 100)
        with self.assertRaises(Exception):
            data.limit = 1

    def test_unknown_duplicate_body_and_collapsed_mapping_rejected(self):
        for pairs in ([('limit', '1'), ('limit', '1')], [('start', '2026-01-01'), ('start', '2026-02-01')],
                      [('sql', 'SELECT 1')], [('role', 'admin')], [('version', 'v')], [('offset', '1')],
                      [('Limit', '1')], {'limit': '1'}, [('facility',)], [([], 'x')]):
            with self.subTest(pairs=pairs):
                self.problem('invalid_request', parse_preview_input, pairs)
        self.problem('invalid_request', parse_preview_input, [], body=b'{}')

    def test_strict_dates_and_limits(self):
        for value in ('', ' ', '20260101', '2026-1-01', '2026-02-29', '2026-01-01T00:00:00',
                      ' 2026-01-01', '0000-01-01', '２０２６-01-01'):
            self.problem('invalid_request', parse_preview_input, [('start', value)])
        for value in ('0', '1001', '01', '+1', '1.0', '1e2', 'True', ' 1', '١', '9'*10000, None):
            self.problem('invalid_request', parse_preview_input, [('limit', value)])
        for value in ('1', '100', '1000'):
            self.assertEqual(parse_preview_input([('limit', value)]).limit, int(value))

    def test_identifier_and_cursor_primitive_bounds(self):
        for name in ('facility', 'generator'):
            for value in ('', '\t', 'x'*129, '\ud800'):
                self.problem('invalid_request', parse_preview_input, [(name, value)])
            self.assertEqual(getattr(parse_preview_input([(name, 'é'*128)]), name), 'é'*128)
        for value in ('', ' ', 'x'*4097, '\ud800'):
            self.problem('invalid_request', parse_preview_input, [('cursor', value)])
        self.assertEqual(len(parse_preview_input([('cursor', 'x'*4096)]).cursor), 4096)
        for changes in ({'limit': True}, {'start': datetime.now()}, {'limit': 0}):
            self.problem('invalid_request', PreviewInput, **changes)

    def test_semantic_validation_is_a_distinct_post_shape_boundary(self):
        # The stage boundary is tested, not real shared rate persistence (Step 3).
        cases = [('national', [('facility', '1')]), ('facility', [('generator', '1'), ('facility', '1')]),
                 ('generator', [('generator', '1')]),
                 ('national', [('start', '2026-10-02'), ('end', '2026-09-03')])]
        for dataset, pairs in cases:
            parsed = parse_preview_input(pairs)
            self.problem('invalid_request', validate_filters, dataset, parsed)
        validate_filters('generator', parse_preview_input([]))
        validate_filters('generator', parse_preview_input([('facility', '01'), ('generator', '1')]))

    def test_default_and_independent_bounds(self):
        latest = date(2026, 10, 2)
        self.assertEqual(resolve_preview('national', parse_preview_input([]), latest), request())
        resolved = resolve_preview('national', parse_preview_input([('start', '2026-09-20')]), latest)
        self.assertEqual((resolved.start, resolved.end), (date(2026, 9, 20), latest))
        resolved = resolve_preview('national', parse_preview_input([('end', '2026-09-10')]), latest)
        self.assertEqual((resolved.start, resolved.end), (date(2026, 9, 3), date(2026, 9, 10)))
        self.problem('invalid_request', resolve_preview, 'national', parse_preview_input([('end', '2026-09-01')]), latest)
        self.problem('dependency_unavailable', resolve_preview, 'national', PreviewInput(), date.min)
        self.problem('dependency_unavailable', resolve_preview, 'national', PreviewInput(), None)

    def test_leap_year_and_no_clamping(self):
        data = parse_preview_input([('start', '2024-01-01'), ('end', '2024-12-31')])
        resolved = resolve_preview('national', data, date(2026, 10, 2))
        self.assertEqual((resolved.end-resolved.start).days+1, 366)
        self.problem('invalid_request', validate_filters, 'national', replace(data, end=date(2025, 1, 1)))
        self.assertEqual(resolved.start, date(2024, 1, 1))

    def test_full_key_shape_bounds_and_binary_order(self):
        req = request('generator', facility='01', generator='2')
        self.assertEqual(validate_key(req, ['2026-09-03', '01', '2']), ('2026-09-03', '01', '2'))
        for key in (['2026-09-03'], ['2026-09-03', '1', '2'], ['2026-09-03', '01', '1'],
                    ['2026-09-02', '01', '2'], ['2026-09-03', 1, '2'], ['20260903', '01', '2']):
            with self.assertRaises(ValueError):
                validate_key(req, key)
        ids = ['2', '10', '1', '01', 'é', 'A', 'a']
        self.assertEqual([key[1] for key in sorted([('2026-09-03', i) for i in ids], key=key_order)],
                         ['01', '1', '10', '2', 'A', 'a', 'é'])


class PreviewCursorTests(SafeAssertions):
    def signed(self, raw, *, key_id='a', secret=KEY):
        if not isinstance(raw, bytes):
            raw = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        prefix = 'pv1.' + key_id + '.' + encoded(raw)
        return prefix + '.' + encoded(hmac.digest(secret, prefix.encode(), hashlib.sha256))

    def payload(self, req=None):
        req = req or request()
        after = ['2026-09-03'] + (['01'] if req.dataset != 'national' else []) + (['1'] if req.dataset == 'generator' else [])
        token = codec().encode(req, PUBLICATION_ID, after)
        return json.loads(base64.urlsafe_b64decode(token.split('.')[2]+'='*(-len(token.split('.')[2])%4)))

    def test_roundtrip_all_datasets_and_full_key(self):
        for dataset in ('national', 'facility', 'generator'):
            req = request(dataset)
            body = self.payload(req)
            position = codec().decode(self.signed(body))
            self.assertEqual(position.request, req)
            self.assertEqual(position.publication_event_id, PUBLICATION_ID)
            self.assertEqual(position.after, tuple(body['after']))
            self.assertEqual(codec().encode(req, PUBLICATION_ID, body['after']), self.signed(body))

    def test_tampered_tokens_fail_before_json_parsing(self):
        token = codec().encode(request(), PUBLICATION_ID, ['2026-09-03'])
        version, kid, payload, tag = token.split('.')
        candidates = ['pv2.'+kid+'.'+payload+'.'+tag, token[:-1]+('A' if token[-1]!='A' else 'B'),
                      '.'.join([version,kid,payload[:-1]+('A' if payload[-1]!='A' else 'B'),tag]),
                      '.'.join([version,'other',payload,tag]), token+'.x', token+'=', 'x'*4097]
        verifier = codec()
        with patch('trinity.queries.cursors._json', side_effect=AssertionError('Unauthenticated JSON parsed')):
            for bad in candidates:
                self.problem('invalid_cursor', verifier.decode, bad)

    def test_valid_mac_does_not_authorize_invalid_payload(self):
        base = self.payload()
        changes = [{'version': True}, {'version': 2}, {'purpose': 'sql'}, {'role': 'admin'},
                   {'dataset': 'national'}, {'dataset': []}, {'publication_event_id': 'not-uuid'},
                   {'publication_event_id': 1}, {'start': '20260903'}, {'limit': True}, {'limit': 1001},
                   {'after': []}, {'after': ['2026-09-02']}, {'after': ['2026-09-03', '1']},
                   {'facility': '1'}, {'generator': '1'}]
        for change in changes:
            with self.subTest(change=change):
                self.problem('invalid_cursor', codec().decode, self.signed({**base, **change}))
        missing = dict(base); del missing['limit']
        self.problem('invalid_cursor', codec().decode, self.signed(missing))
        req = request('generator', facility='01', generator='1')
        body = self.payload(req); body['after'][1] = '99'
        self.problem('invalid_cursor', codec().decode, self.signed(body))

    def test_noncanonical_duplicate_deep_and_unicode_json_rejected(self):
        canonical = json.dumps(self.payload(), sort_keys=True, separators=(',', ':'))
        cases = [json.dumps(self.payload()).encode(),
                 canonical.replace('"version":1', '"version":1,"version":1').encode(),
                 b'['*1100+b']'*1100, b'{"a":NaN}', b'\xff', b'"'+b'x'*2999+b'"',
                 canonical.replace('"facility":null', '"facility":"\\ud800"').encode()]
        for raw in cases:
            self.problem('invalid_cursor', codec().decode, self.signed(raw))

    def test_restart_rotation_retirement_and_header_authentication(self):
        token = codec().encode(request(), PUBLICATION_ID, ['2026-09-03'])
        restarted = CursorCodec(load_cursor_keys(environment()))
        self.assertEqual(restarted.decode(token).after, ('2026-09-03',))
        rotated = CursorCodec(load_cursor_keys(environment('b', {'a': KEY, 'b': OTHER_KEY})))
        self.assertEqual(rotated.decode(token).request, request())
        self.assertTrue(rotated.encode(request(), PUBLICATION_ID, ['2026-09-03']).startswith('pv1.b.'))
        retired = CursorCodec(load_cursor_keys(environment('b', {'b': OTHER_KEY})))
        self.problem('invalid_cursor', retired.decode, token)
        self.problem('invalid_cursor', rotated.decode, token.replace('pv1.a.', 'pv1.b.'))
        same_bytes_other_id = CursorCodec(load_cursor_keys(environment('b', {'a': KEY, 'b': KEY})))
        self.problem('invalid_cursor', same_bytes_other_id.decode, token.replace('pv1.a.', 'pv1.b.'))
        self.assertNotIn('exp', self.payload())
        self.assertNotIn('iat', self.payload())

    def test_configuration_is_lazy_bounded_and_secret_safe(self):
        keys = load_cursor_keys(environment())
        self.assertNotIn(encoded(KEY), repr(keys))
        self.assertNotIn(repr(KEY), repr(keys.keys))
        self.assertIsInstance(keys.keys, MappingProxyType)
        with self.assertRaises(TypeError):
            keys.keys['a'] = SecretBytes(OTHER_KEY)
        bad = [{}, environment('missing'), environment(keys={str(i): KEY for i in range(5)}),
               environment(keys={'a': b'short'}), environment(keys={'bad.id': KEY})]
        for raw in ('{}', '[]', '{"a":"canary"}', '{"a":null}', '{"a":NaN}',
                    '{"a":"'+encoded(KEY)+'","a":"'+encoded(KEY)+'"}', 'x'*4097, '['*1100+']'*1100):
            bad.append({'TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID':'a','TRINITY_PREVIEW_CURSOR_KEYS_JSON':raw})
        for env in bad:
            self.problem('dependency_unavailable', load_cursor_keys, env)
        with patch.dict(os.environ, environment(), clear=True):
            self.assertEqual(load_cursor_keys().active_id, 'a')
        with patch.dict(os.environ, {}, clear=True):
            self.problem('dependency_unavailable', load_cursor_keys)

    def test_maximum_unicode_payload_fits_and_empty_runtime_authority(self):
        entity = '\U0010ffff'*128
        req = request('generator', facility=entity, generator=entity, limit=1000)
        token = codec().encode(req, PUBLICATION_ID, ['2026-09-03',entity,entity])
        self.assertLessEqual(len(token), 4096)
        self.assertEqual(codec().decode(token).request, req)
        for field in ('sql','role','path','credentials','user_id'):
            self.assertNotIn(field, self.payload())

    def test_continuation_publication_precedes_default_resolution(self):
        position = codec().decode(codec().encode(request(), PUBLICATION_ID, ['2026-09-03']))
        self.assertEqual(resolve_continuation(position, 'national', PreviewInput(), publication()), request())
        explicit = parse_preview_input([('start','2026-09-03'),('end','2026-10-02'),('limit','100')])
        self.assertEqual(resolve_continuation(position, 'national', explicit, publication()), request())
        changed = publication(publication_event_id=VERSION_ID, latest_observation_date=date(2026, 9, 20))
        self.problem('publication_changed', resolve_continuation, position, 'national', PreviewInput(end=date(2026,1,1)), changed, status=409)
        self.problem('publication_changed', resolve_continuation, position, 'national', PreviewInput(), None)
        self.problem('invalid_cursor', resolve_continuation, position, 'facility', PreviewInput(), publication())
        self.problem('invalid_cursor', resolve_continuation, position, 'national', PreviewInput(limit=10), publication())

    def test_entity_filter_and_page_size_must_be_repeated(self):
        req = request('generator', facility='01', generator='1', limit=1)
        position = codec().decode(codec().encode(req, PUBLICATION_ID, ['2026-09-03','01','1']))
        data = PreviewInput(facility='01', generator='1', limit=1)
        self.assertEqual(resolve_continuation(position,'generator',data,publication()),req)
        for changed in (PreviewInput(), replace(data, limit=100), replace(data, generator='2')):
            self.problem('invalid_cursor',resolve_continuation,position,'generator',changed,publication())
        self.problem('dataset_not_found',authorize_preview,Principal('v','viewer','s'),'generator_outages')


class PreviewResponseTests(SafeAssertions):
    def test_native_values_roundtrip_with_canonical_columns(self):
        for dataset in ('national','facility','generator'):
            rows = serialize_preview_rows(dataset,[native_row(dataset,facility='001',generator='01')])
            result = page(request(dataset),rows)
            self.assertEqual(result.columns,describe_dataset(dataset).columns)
            self.assertIn('-0.000001',result.rows[0])
            self.assertIn('100.000001',result.rows[0])
            self.assertIsNone(result.rows[0][-1])
            self.assertEqual(PreviewResponse.model_validate_json(result.model_dump_json()),result)
            self.assertTrue(json.loads(result.model_dump_json())['publication']['published_at'].endswith('Z'))

    def test_serializer_never_rounds_or_accepts_float_nonfinite_overflow(self):
        for bad in (1.5,1,'1.0',Decimal('NaN'),Decimal('Infinity'),Decimal('1e18'),Decimal('1.0000001')):
            self.problem('dependency_unavailable',serialize_preview_rows,'national',[native_row(outage=bad)])
        self.problem('dependency_unavailable',serialize_preview_rows,'national',[native_row(capacity=Decimal('-1'))])
        self.problem('dependency_unavailable',serialize_preview_rows,'national',[native_row(period=datetime.now())])
        self.problem('dependency_unavailable',serialize_preview_rows,'facility',[native_row('facility',facility=1)])
        self.problem('dependency_unavailable',serialize_preview_rows,'national',[native_row(capacity=None)])
        with localcontext() as context:
            context.prec=6
            rows=serialize_preview_rows('national',[native_row(capacity=Decimal('999999999999999999.999999'))])
        self.assertEqual(rows[0][1],'999999999999999999.999999')

    def test_empty_requires_reason_and_explicit_diagnostics(self):
        result=page(rows=[])
        self.assertEqual((result.rows,result.returned_rows,result.next_cursor,result.reason),([],0,None,'not_reported'))
        body=result.model_dump(); del body['diagnostics']
        with self.assertRaises(ValidationError):PreviewResponse.model_validate(body)
        self.problem('dependency_unavailable',page,request(),[],after=['2026-09-03'])
        with self.assertRaises(TypeError):
            build_preview_response(request(),publication(),[],codec=codec())

    def test_lookahead_bound_and_cursor_uses_last_returned_key(self):
        req=request(limit=2)
        for count in (0,1,2,3):
            result=page(req,wire_rows(count=count))
            self.assertEqual(result.returned_rows,min(count,2))
            self.assertEqual(result.next_cursor is not None,count>2)
            if count>2:self.assertEqual(codec().decode(result.next_cursor).after,('2026-09-04',))
        self.problem('dependency_unavailable',page,req,wire_rows(count=4))
        req=request('generator',limit=1)
        rows=serialize_preview_rows('generator',[native_row('generator',generator=g) for g in ('1','10')])
        first=page(req,rows)
        self.assertEqual(codec().decode(first.next_cursor).after,('2026-09-03','01','1'))
        second=page(req,rows[1:],after=codec().decode(first.next_cursor).after)
        self.assertIsNone(second.next_cursor)
        self.assertEqual(first.rows+second.rows,rows)

    def test_maximum_page_returns_1000_not_lookahead(self):
        req=request('facility',limit=1000)
        rows=serialize_preview_rows('facility',[native_row('facility',facility=f'{i:04}') for i in range(1001)])
        result=page(req,rows)
        self.assertEqual(result.returned_rows,1000)
        self.assertEqual(codec().decode(result.next_cursor).after,('2026-09-03','0999'))
        self.assertIsNone(page(req,rows[:1000]).next_cursor)

    def test_order_filters_and_after_are_validated_including_lookahead(self):
        req=request('generator',facility='01',generator='1',limit=1)
        row=serialize_preview_rows('generator',[native_row('generator')])[0]
        bad_rows=[[row,row], [row,serialize_preview_rows('generator',[native_row('generator',facility='02')])[0]]]
        for rows in bad_rows:self.problem('dependency_unavailable',page,req,rows)
        self.problem('dependency_unavailable',page,req,[row],after=['2026-09-03','01','1'])
        self.problem('dependency_unavailable',page,request(),list(reversed(wire_rows(count=2))))
        outside=wire_rows(); outside[0][0]='2023-01-01'
        self.problem('dependency_unavailable',page,request(start=date(2023,1,1),end=date(2023,1,2)),outside)

    def test_diagnostic_registry_privacy_and_no_implicit_empty(self):
        item=PreviewDiagnostic(code='D03',severity='warning',scope='national',message=MESSAGES['D03'],affected_count='1')
        self.assertEqual(page(diagnostics=[item]).diagnostics,[item])
        detail=item.model_copy(update={'scope':'facility'})
        self.problem('dependency_unavailable',page,diagnostics=[detail])
        self.problem('dependency_unavailable',page,diagnostics=[item,item])
        for changes in ({'code':'D99'},{'code':'D09'},{'scope':'all'},{'message':'hidden canary'},
                        {'severity':'info'},{'affected_count':'01'},{'affected_count':1}):
            with self.assertRaises(ValidationError):PreviewDiagnostic.model_validate({**item.model_dump(),**changes})
        with self.assertRaises(ValidationError):PreviewDiagnostic(code='D01',severity='warning',scope='national',message=MESSAGES['D01'],affected_count='1')

    def test_response_rejects_wire_schema_and_state_corruption(self):
        base=page().model_dump()
        for changes in ({'extra':'x'},{'returned_rows':2},{'returned_rows':True},{'reason':'not_reported'},
                        {'columns':list(reversed(base['columns']))},{'rows':[['2026-09-03']]},
                        {'rows':[['2026-09-03','100.000001',False,None]]},
                        {'rows':[['2026-09-03','100.000001','1e2',None]]},
                        {'rows':[['20260903','100.000001','1.000000',None]]},
                        {'next_cursor':' '},{'next_cursor':'x'*4097},
                        {'publication':publication(published_at=datetime(2026,10,3))}):
            with self.subTest(changes=changes):
                with self.assertRaises((ValidationError,ValueError)):PreviewResponse.model_validate({**base,**changes})
        body=page(rows=[]).model_dump(); body['reason']=None
        with self.assertRaises(ValidationError):PreviewResponse.model_validate(body)

    def test_whole_envelope_size_limit_counts_metadata(self):
        req=request('facility',limit=1)
        row=serialize_preview_rows('facility',[native_row('facility')])[0]
        row[2]='x'*MAX_RESPONSE_BYTES
        self.problem('query_resource_limit',page,req,[row],status=503)
        row[2]='é'*(MAX_RESPONSE_BYTES//2)
        self.problem('query_resource_limit',page,req,[row])
        row[2]='x'*(MAX_RESPONSE_BYTES-4096)
        self.assertLessEqual(len(page(req,[row]).model_dump_json().encode()),MAX_RESPONSE_BYTES)

    def test_imports_need_no_configuration_and_do_not_load_execution(self):
        code='''import sys
from trinity.queries import preview, cursors, preview_schemas
assert 'trinity.queries.client' not in sys.modules
assert 'trinity.queries.runtime.engine' not in sys.modules
assert 'trinity.adapters.s3' not in sys.modules
assert preview.parse_preview_input([]).limit == 100
print('offline import passed')
'''
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,
                              env={'PATH':os.environ.get('PATH','')},timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'offline import passed')


if __name__=='__main__':
    unittest.main()
