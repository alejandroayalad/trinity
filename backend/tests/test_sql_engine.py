"""Execute validated SQL on real synthetic Parquet with pinned DataFusion."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trinity.queries.runtime.engine import execute_local, QueryExecutionError
from trinity.queries.runtime.sql_policy import validate_query
from sql_fixture import write_table

CASES = json.loads((Path(__file__).parent / 'fixtures/sql_review_cases.json').read_text())['cases']


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for key in ('national', 'facility', 'generator'):
            write_table(self.root / key, key)

    def execute(self, sql):
        query = validate_query(sql)
        return execute_local(query, self.root / query.dataset)

    def test_every_allowed_review_case_executes(self):
        for case in CASES:
            if case['expectation'] != 'allow': continue
            with self.subTest(case=case['id']):
                result = self.execute(case['sql'])
                self.assertEqual(result['returned_rows'], len(result['rows']))

    def test_exact_numbers_nulls_duplicates_and_units(self):
        result = self.execute('SELECT outage AS value, capacity AS value, percentOutage, outage / 3 FROM national_outages ORDER BY period')
        self.assertEqual([c['name'] for c in result['columns']], ['value', 'value', 'percentOutage', 'expression_1'])
        self.assertEqual(result['rows'][0][:3], ['1.000000', '100.000000', None])
        self.assertEqual(result['columns'][0]['unit'], 'MW')
        self.assertIsNone(result['columns'][3]['unit'])
        self.assertIsInstance(result['rows'][0][3], str)
        self.assertTrue(result['rows'][0][3].startswith('0.333333'))

    def test_aggregate_input_is_not_capped_and_query_limit_is_preserved(self):
        write_table(self.root / 'national', count=1005)
        result = self.execute('SELECT COUNT(*) FROM national_outages')
        self.assertEqual(result['rows'], [['1005']])
        self.assertFalse(result['truncated'])
        self.assertTrue(self.execute('SELECT period FROM national_outages')['truncated'])
        self.assertFalse(self.execute('SELECT period FROM national_outages LIMIT 1000')['truncated'])
        self.assertEqual(self.execute('SELECT period FROM national_outages LIMIT 0')['rows'], [])

    def test_null_order_defaults_and_explicit_override(self):
        default = self.execute('SELECT percentOutage FROM national_outages ORDER BY percentOutage DESC')
        explicit = self.execute('SELECT percentOutage FROM national_outages ORDER BY percentOutage DESC NULLS FIRST')
        self.assertIsNone(default['rows'][-1][0])
        self.assertIsNone(explicit['rows'][0][0])

    def test_message_tampering_fails_before_engine_creation(self):
        good = validate_query('SELECT outage FROM national_outages')
        with patch('trinity.queries.runtime.engine.SessionContext') as context:
            for query in (replace(good, operation='SELECT * FROM local_users'), replace(good, dataset='facility')):
                with self.assertRaises(QueryExecutionError): execute_local(query, self.root / 'national')
            context.assert_not_called()

    def test_division_by_zero_returns_safe_failure(self):
        with self.assertRaises(QueryExecutionError) as caught:
            self.execute('SELECT outage / 0 FROM national_outages')
        self.assertEqual(str(caught.exception), 'query_failed')

    def test_round_and_average_precision(self):
        result = self.execute('SELECT AVG(outage), ROUND(AVG(outage), 2), SUM(outage) FROM national_outages')
        self.assertEqual([Decimal(x) for x in result['rows'][0]], [Decimal('2'), Decimal('2'), Decimal('6')])
        self.assertTrue(all(c['type'] == 'decimal' for c in result['columns']))

    def test_round_ties_scale_range_overflow_and_empty_aggregates(self):
        write_table(self.root / 'national', values=[{'outage': Decimal('1.250000')},
                    {'outage': Decimal('-1.250000')}, {'outage': Decimal('999999999999999999.999999')}])
        result = self.execute('SELECT ROUND(outage, 1) FROM national_outages ORDER BY period')
        self.assertEqual(result['rows'], [['1.3'], ['-1.3'], ['1000000000000000000.0']])
        for scale in range(-18, 19):
            with self.subTest(scale=scale):
                self.execute(f'SELECT ROUND(outage, {scale}) FROM national_outages')
        with self.assertRaises(QueryExecutionError):
            self.execute('SELECT outage * outage FROM national_outages')
        result = self.execute('SELECT COUNT(*), SUM(outage), AVG(outage) FROM national_outages WHERE FALSE')
        self.assertEqual(result['rows'], [['0', None, None]])

    def test_output_byte_budget_fails_without_partial_result(self):
        write_table(self.root / 'national', count=1000)
        with self.assertRaises(QueryExecutionError) as caught:
            self.execute("SELECT '" + 'x' * 10000 + "' FROM national_outages")
        self.assertEqual(caught.exception.code, 'query_resource_limit')

    def test_canonical_qualifier_resolves_even_with_a_table_alias(self):
        result=self.execute('SELECT national_outages.outage FROM national_outages n ORDER BY national_outages.period')
        self.assertEqual(result['rows'][0],['1.000000'])
