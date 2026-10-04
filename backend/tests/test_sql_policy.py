"""Prove the closed grammar before any storage or engine call."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from trinity.contracts.queries import ValidatedQuery
from trinity.queries.policy import validate_in_process, _SLOTS
from trinity.queries.runtime.sql_policy import SQLValidationError, validate_query

CASES = json.loads((Path(__file__).parent / "fixtures/sql_review_cases.json").read_text())["cases"]


class SqlPolicyTests(unittest.TestCase):
    def test_complete_review_matrix(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                if case["expectation"] == "allow":
                    self.assertIsInstance(validate_query(case["sql"]), ValidatedQuery)
                elif case["expectation"] == "reject":
                    with self.assertRaises(SQLValidationError):
                        validate_query(case["sql"])

    def test_exact_labels_units_and_order_normalization(self):
        result = validate_query('SELECT outage AS value, capacity AS value, outage + 1 FROM national_outages ORDER BY outage DESC')
        self.assertEqual([(c.name, c.unit) for c in result.columns], [("value", "MW"), ("value", "MW"), ("expression_1", None)])
        self.assertIn('"outage" DESC NULLS LAST', result.operation)
        explicit = validate_query('SELECT outage FROM national_outages ORDER BY outage DESC NULLS FIRST')
        self.assertIn('"outage" DESC NULLS FIRST', explicit.operation)
        self.assertNotEqual(result.digest, explicit.digest)

    def test_star_and_order_alias_are_normalized(self):
        result = validate_query('SELECT n.*, outage + 1 AS calculated FROM national_outages AS n ORDER BY calculated')
        self.assertEqual([c.name for c in result.columns], ["period", "capacity", "outage", "percentOutage", "calculated"])
        self.assertIn('ORDER BY "__trinity_c004" ASC NULLS LAST', result.operation)

    def test_nested_unsupported_forms_and_erased_syntax_are_rejected(self):
        examples = [
            'SELECT outage value FROM national_outages',
            'SELECT ALL outage FROM national_outages',
            'SELECT SUM(ALL outage) FROM national_outages',
            'SELECT outage FROM national_outages FETCH FIRST 1 ROW ONLY',
            'SELECT outage FROM national_outages ORDER BY outage USING >',
            'SELECT outage FROM national_outages WHERE TRUE OR EXISTS(SELECT 1)',
            'SELECT CASE WHEN TRUE THEN ABS(outage) END FROM national_outages',
            'SELECT "Outage" FROM national_outages',
            'SELECT x.outage FROM national_outages n',
            'SELECT ROUND(outage, 1.5) FROM national_outages',
            'SELECT SUM(facilityName) FROM facility_outages',
            'SELECT period, SUM(outage) FROM national_outages',
            'SELECT outage FROM national_outages GROUP BY period',
            'SELECT SUM(outage) FROM national_outages ORDER BY period',
            'SELECT outage FROM national_outages WHERE SUM(outage) > 1',
            'SELECT * EXCEPT (outage) FROM national_outages',
            'SELECT outage FROM national_outages TABLESAMPLE BERNOULLI(10)',
            'SELECT 1e2 FROM national_outages',
            'SELECT outage FROM national_outages; /*+ hint */',
        ]
        for sql in examples:
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_query(sql)

    def test_comment_or_string_keywords_do_not_trigger_false_rejection(self):
        validate_query("SELECT 'CAST NVL SELECT https://example.invalid' AS note FROM national_outages; -- CAST NVL")
        validate_query('SELECT outage AS "CAST" FROM national_outages ORDER BY "CAST"')

    def test_input_and_ast_limits(self):
        for sql in (' ' * 16385, 'SELECT ' + '(' * 65 + '1' + ')' * 65 + ' FROM national_outages',
                    'SELECT ' + ','.join(['outage'] * 129) + ' FROM national_outages',
                    '\ud800', 'SELECT ' + 'NOT ' * 80 + 'TRUE FROM national_outages'):
            with self.subTest(size=len(sql)), self.assertRaises(SQLValidationError):
                validate_query(sql)

    def test_message_is_closed_and_canonical(self):
        result = validate_query('SELECT outage FROM national_outages')
        self.assertEqual(ValidatedQuery.from_bytes(result.to_bytes()), result)
        self.assertNotIn('SELECT', repr(result))
        with self.assertRaises(ValueError):
            ValidatedQuery.from_bytes(result.to_bytes() + b' ')

    def test_actual_subprocess_and_rejection(self):
        sql = 'SELECT outage FROM national_outages'
        with patch.dict('os.environ', {'TRINITY_SECRET_TEST': 'synthetic'}):
            self.assertEqual(validate_in_process(sql), validate_query(sql))
        with self.assertRaises(SQLValidationError):
            validate_in_process('SELECT * FROM local_users')

    def test_timeout_terminates_child_and_capacity_has_no_queue(self):
        with self.assertRaises(SQLValidationError):
            validate_in_process('SELECT outage FROM national_outages', timeout=0.00001)
        _SLOTS.acquire(); _SLOTS.acquire()
        try:
            with self.assertRaises(SQLValidationError):
                validate_in_process('SELECT outage FROM national_outages')
        finally:
            _SLOTS.release(); _SLOTS.release()
        self.assertIsInstance(validate_in_process('SELECT outage FROM national_outages'), ValidatedQuery)
