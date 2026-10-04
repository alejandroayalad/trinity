"""Exercise only the whole-input, single-SELECT gate with synthetic SQL."""

import json
from pathlib import Path
import traceback
import unittest

from sqlglot import exp

from trinity.queries.runtime.sql_policy import SQLValidationError, validate_single_statement


FIXTURES = Path(__file__).parent / "fixtures" / "sql_review_cases.json"
CASES = {case["id"]: case for case in json.loads(FIXTURES.read_text())["cases"]}


class SingleStatementTests(unittest.TestCase):
    def test_a01_returns_the_complete_select(self):
        statement = validate_single_statement(CASES["A01"]["sql"])
        self.assertIsInstance(statement, exp.Select)
        self.assertEqual([column.name for column in statement.expressions], ["period", "outage"])
        self.assertEqual(statement.args["from_"].this.name, "national_outages")
        self.assertEqual(statement.args["order"].expressions[0].this.name, "period")
        self.assertEqual(statement.args["limit"].expression.this, "10")

    def test_b01_and_b02_reject_the_second_statement(self):
        for case_id in ("B01", "B02"):
            with self.subTest(case=case_id), self.assertRaises(SQLValidationError):
                validate_single_statement(CASES[case_id]["sql"])

    def test_one_trailing_semicolon_passes(self):
        statement = validate_single_statement("SELECT outage FROM national_outages;")
        self.assertIsInstance(statement, exp.Select)

    def test_original_b03_rejects_extra_empty_statement(self):
        with self.assertRaises(SQLValidationError):
            validate_single_statement(CASES["B03"]["sql"])

    def test_empty_and_comment_only_inputs_are_rejected(self):
        for sql in ("", " \n\t", "-- comment", "/* comment */", ";", "; -- comment"):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_single_statement(sql)

    def test_non_select_roots_are_rejected(self):
        for sql in ("DELETE FROM national_outages", "DROP TABLE national_outages",
                    "SELECT 1 UNION SELECT 2"):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_single_statement(sql)

    def test_syntax_and_token_errors_do_not_expose_sql(self):
        for sql in ("SELECT private_marker FROM", "SELECT 'private_marker",
                    "SELECT outage FROM national_outages; /* private_marker"):
            with self.subTest(sql=sql):
                try:
                    validate_single_statement(sql)
                except SQLValidationError as error:
                    self.assertEqual(str(error), "Invalid SQL syntax.")
                    rendered = "".join(traceback.format_exception(error))
                    self.assertNotIn("private_marker", rendered)
                else:
                    self.fail("Malformed SQL passed the check.")

    def test_semicolons_inside_literals_and_comments_are_not_statements(self):
        statement = validate_single_statement(
            "/* ; */ SELECT '; DELETE FROM local_users' FROM national_outages -- ;"
        )
        self.assertIsInstance(statement, exp.Select)

    def test_a24_trailing_comment_passes_and_comments_are_preserved(self):
        statement = validate_single_statement(CASES["A24"]["sql"])
        self.assertIsInstance(statement, exp.Select)
        self.assertIn(" ordinary comment ", statement.comments)
        self.assertIn(" done", statement.comments)

    def test_terminal_semicolon_accepts_only_whitespace_and_comments_after_it(self):
        suffixes = (" \n\t", " -- done", " /* done */", " -- ; SELECT 2\n /* ; */",
                    " /* outer /* nested ; */ done */ -- final\n")
        for suffix in suffixes:
            with self.subTest(suffix=suffix):
                statement = validate_single_statement("SELECT outage FROM national_outages;" + suffix)
                self.assertIsInstance(statement, exp.Select)

    def test_second_semicolon_or_statement_after_comments_is_rejected(self):
        suffixes = (";", " /* comment */ ;", " -- comment\n;", " /* comment */ SELECT 1",
                    " -- comment\n DELETE FROM national_outages", " /* comment */ outage")
        for suffix in suffixes:
            with self.subTest(suffix=suffix), self.assertRaises(SQLValidationError):
                validate_single_statement("SELECT outage FROM national_outages;" + suffix)

    def test_leading_semicolon_is_not_a_terminal_semicolon(self):
        for sql in ("; SELECT 1", "/* comment */ ; SELECT 1;"):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                validate_single_statement(sql)

    def test_quoted_semicolons_do_not_count_as_terminators(self):
        for sql in ("SELECT ';' FROM national_outages; -- done",
                    'SELECT outage AS "semi;colon" FROM national_outages;',
                    "SELECT $$; SELECT 2$$ FROM national_outages; /* done */"):
            with self.subTest(sql=sql):
                self.assertIsInstance(validate_single_statement(sql), exp.Select)

    def test_single_select_is_not_full_policy_authorization(self):
        for case_id in ("B04", "B05", "B09", "B19"):
            with self.subTest(case=case_id):
                self.assertIsInstance(validate_single_statement(CASES[case_id]["sql"]), exp.Select)


if __name__ == "__main__":
    unittest.main()
