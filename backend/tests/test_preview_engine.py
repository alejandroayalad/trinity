"""Use real DataFusion and temporary synthetic Parquet; no Docker or S3."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from trinity.contracts.queries import (
    BINDING_FIELDS, PreviewOperation, canonical_message, read_request,
    read_result_binding, request_message,
)
from trinity.queries.preview_schemas import build_preview_batch_response
from trinity.queries.runtime.__main__ import run_request
from trinity.queries.runtime.preview import execute_preview
from trinity.queries.runtime.engine import QueryExecutionError
from trinity.queries.runtime.sql_policy import validate_query
from trinity.errors import Problem
from sql_fixture import write_table
from test_preview_unit import codec, publication


def operation(dataset='national', **changes):
    values = dict(dataset=dataset, publication_event_id=str(publication().publication_event_id),
                  version_id=str(publication().version_id), start='2025-01-01', end='2025-01-03', page_size=2)
    return PreviewOperation(**(values | changes))


class PreviewEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_all_schemas_exact_scalars_and_pagination(self):
        for dataset in ('national', 'facility', 'generator'):
            with self.subTest(dataset=dataset):
                write_table(self.root / dataset, dataset, values=[{
                    'outage': Decimal('-0.000001'), 'capacity': Decimal('999999999999999999.999999'),
                    'percentOutage': None, 'facilityName': None}])
                first = execute_preview(operation(dataset), self.root / dataset)
                response = build_preview_batch_response(operation(dataset), publication(), first,
                                                        diagnostics=[], codec=codec())
                self.assertEqual(response.returned_rows, 2)
                self.assertTrue(first['has_more'])
                self.assertIn('-0.000001', first['rows'][0])
                self.assertIn('999999999999999999.999999', first['rows'][0])
                position = codec().decode(response.next_cursor)
                second_op = operation(dataset, after=position.after)
                second = execute_preview(second_op, self.root / dataset)
                self.assertEqual(len(second['rows']), 1)
                self.assertFalse(second['has_more'])
                self.assertEqual(second['rows'][0][0], '2025-01-03')

    def test_full_key_binary_order_preserves_same_day_entities(self):
        values = [{'period': date(2025, 1, 1), 'facility': f, 'generator': g}
                  for f in ('é', '01', 'a', 'A', '😀', '1') for g in ('10', '01', '2')]
        for dataset in ('facility', 'generator'):
            rows = values if dataset == 'generator' else values[::3]
            write_table(self.root / dataset, dataset, count=len(rows), values=rows)
            op = operation(dataset, page_size=1)
            keys = []
            while True:
                batch = execute_preview(op, self.root / dataset)
                names = [column['name'] for column in batch['columns']]
                key_names = ('period', 'facility', 'generator') if dataset == 'generator' else ('period', 'facility')
                key = tuple(batch['rows'][0][names.index(name)] for name in key_names)
                keys.append(key)
                if not batch['has_more']:
                    break
                op = replace(op, after=key)
            expected = sorted({tuple(str(row[name]) for name in key_names) for row in rows},
                              key=lambda key: tuple(part.encode('utf-8') for part in key))
            self.assertEqual(keys, expected)

    def test_filters_are_literals_and_dates_are_inclusive(self):
        literal = "01' OR TRUE --"
        write_table(self.root / 'generator', 'generator', values=[
            {'facility': literal, 'generator': '01'}, {'facility': '01', 'generator': '01'},
            {'facility': literal, 'generator': '1'}])
        op = operation('generator', facility=literal, generator='01')
        batch = execute_preview(op, self.root / 'generator')
        self.assertEqual(len(batch['rows']), 1)
        self.assertEqual(batch['rows'][0][0], '2025-01-01')
        self.assertEqual(execute_preview(replace(op, start='2025-01-02'), self.root / 'generator')['rows'], [])

    def test_invalid_operation_is_rejected_before_context(self):
        op = operation()
        object.__setattr__(op, 'page_size', True)
        with patch('trinity.queries.runtime.preview.restricted_context') as context:
            with self.assertRaises(QueryExecutionError):
                execute_preview(op, self.root)
            context.assert_not_called()

    def test_response_rejects_bad_batch_order_filters_and_empty_continuation(self):
        write_table(self.root, 'national')
        op = operation()
        batch = execute_preview(op, self.root)
        for bad in (dict(batch, has_more=1), dict(batch, has_more=None),
                    dict(batch, rows=list(reversed(batch['rows']))), dict(batch, extra='hidden'),
                    dict(batch, columns=[]), dict(batch, rows=batch['rows'][:1])):
            with self.subTest(bad=bad.keys()), self.assertRaises(Problem):
                build_preview_batch_response(op, publication(), bad, diagnostics=[], codec=codec())
        with self.assertRaises(Problem):
            build_preview_batch_response(replace(op, after=('2025-01-02',)), publication(),
                                         dict(batch, rows=[], has_more=False), diagnostics=[], codec=codec())

    def test_exact_page_boundary_and_output_limit(self):
        write_table(self.root, 'national', count=2)
        self.assertFalse(execute_preview(operation(), self.root)['has_more'])
        write_table(self.root, 'facility', count=1, values=[{'facilityName': 'x' * (5 * 1024 * 1024)}])
        with self.assertRaises(QueryExecutionError) as caught:
            execute_preview(operation('facility'), self.root)
        self.assertEqual(caught.exception.code, 'query_resource_limit')


class RuntimeProtocolTests(unittest.TestCase):
    def test_runtime_imports_no_trusted_api_or_credential_modules(self):
        import subprocess
        import sys
        check = subprocess.run([sys.executable, '-c',
            "import sys; import trinity.queries.runtime.__main__; "
            "assert not any(name.startswith(('trinity.auth', 'trinity.queries.cursors', "
            "'trinity.queries.config', 'trinity.adapters', 'boto3', 'psycopg')) for name in sys.modules)"],
            capture_output=True, timeout=10)
        self.assertEqual(check.returncode,0,check.stderr.decode())

    def test_sql_and_preview_dispatch_preserve_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_table(root)
            for op in (operation(), validate_query('SELECT outage FROM national_outages')):
                message = request_message(uuid4(), op.version_id if isinstance(op, PreviewOperation) else uuid4(), op)
                response = run_request(canonical_message(message), root)
                self.assertEqual({k: response[k] for k in BINDING_FIELDS}, {k: message[k] for k in BINDING_FIELDS})
                read_result_binding(response, message['request_id'], message['version_id'], op)

    def test_wrong_kind_version_digest_and_extensions_fail_before_execution(self):
        op = operation()
        message = request_message(uuid4(), op.version_id, op)
        variants = [dict(message, operation_kind='sql'), dict(message, protocol_version=True),
                    dict(message, protocol_version=2), dict(message, operation_kind='unknown'),
                    dict(message, operation_digest='0'*64), dict(message, version_id=str(uuid4())),
                    dict(message, policy=message['operation'])]
        for bad in variants:
            with self.subTest(bad=bad), patch('trinity.queries.runtime.__main__.execute_preview') as run:
                with self.assertRaises(ValueError):
                    run_request(canonical_message(bad), Path('/unused'))
                run.assert_not_called()
        with self.assertRaises(ValueError):
            read_request(canonical_message(message) + b' ')
        response = {k: message[k] for k in BINDING_FIELDS} | {'result': {}}
        for key, value in (('operation_kind','sql'), ('request_id',str(uuid4())), ('protocol_version',True)):
            with self.assertRaises(ValueError):
                read_result_binding(dict(response, **{key:value}), message['request_id'], message['version_id'], op)
