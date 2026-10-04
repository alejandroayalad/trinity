"""Characterize SQLGlot shapes for human review, without authorizing any SQL.

Only bundled synthetic examples are parsed. These checks do not invoke a
validator, DataFusion, files from a publication, or application services.
"""

import json
from pathlib import Path
import unittest

import sqlglot
from sqlglot import Dialect, ErrorLevel, exp


FIXTURES = Path(__file__).parent / "fixtures" / "sql_review_cases.json"
CASES = {case["id"]: case for case in json.loads(FIXTURES.read_text())["cases"]}


def parse_example(case_id):
    """Return a complete parse of one bundled example, not a policy decision."""
    return sqlglot.parse(
        CASES[case_id]["sql"], read="postgres", error_level=ErrorLevel.IMMEDIATE,
        max_errors=1, max_nodes=4096,
    )


class SqlReviewScaffoldTests(unittest.TestCase):
    def test_parse_keeps_a_trailing_write_and_an_empty_statement(self):
        trees = parse_example("B01")
        self.assertEqual([type(tree) for tree in trees], [exp.Select, exp.Delete])
        trees = parse_example("B03")
        self.assertEqual(len(trees), 2)
        self.assertIsInstance(trees[0], exp.Select)
        self.assertIsNone(trees[1])

    def test_typed_date_and_explicit_cast_have_equal_expression_trees(self):
        typed_date = parse_example("A10")[0].expressions[0]
        explicit_cast = parse_example("B23")[0].expressions[0]
        self.assertIsInstance(typed_date, exp.Cast)
        self.assertEqual(typed_date, explicit_cast)
        dialect = Dialect.get_or_raise("postgres")
        date_tokens = dialect.tokenize(CASES["A10"]["sql"])
        cast_tokens = dialect.tokenize(CASES["B23"]["sql"])
        self.assertEqual(date_tokens[1].token_type.name, "DATE")
        self.assertEqual(cast_tokens[1].text, "CAST")

    def test_omitted_and_explicit_null_order_have_equal_order_nodes(self):
        omitted = parse_example("A21")[0].args["order"].expressions[0]
        explicit = parse_example("A22")[0].args["order"].expressions[0]
        self.assertEqual(omitted, explicit)
        self.assertTrue(omitted.args["nulls_first"])
        # PostgreSQL parser defaults are different from Trinity's D03 default.

    def test_unapproved_function_spellings_normalize_to_coalesce(self):
        for case_id in ("A17", "B21", "B22"):
            with self.subTest(case=case_id):
                expression = parse_example(case_id)[0].expressions[0]
                self.assertIsInstance(expression, exp.Coalesce)
                source = CASES[case_id]["sql"]
                start, end = expression.meta["start"], expression.meta["end"]
                expected = {"A17": "COALESCE", "B21": "NVL", "B22": "IFNULL"}
                self.assertEqual(source[start:end + 1], expected[case_id])

    def test_a_table_node_can_wrap_a_file_reader(self):
        tree = parse_example("B17")[0]
        table = tree.args["from_"].this
        self.assertIsInstance(table, exp.Table)
        self.assertIsInstance(table.this, exp.ReadParquet)
        self.assertNotIsInstance(table.this, exp.Identifier)

    def test_comma_from_is_a_join_and_in_subquery_has_a_query_argument(self):
        tree = parse_example("B10")[0]
        self.assertIsInstance(tree.args["joins"][0], exp.Join)
        tree = parse_example("B14")[0]
        predicate = tree.args["where"].this
        self.assertIsInstance(predicate, exp.In)
        self.assertIsInstance(predicate.args["query"], exp.Subquery)

    def test_hint_and_scientific_notation_need_more_than_node_names(self):
        tree = parse_example("B44")[0]
        self.assertIn("+ hint ", tree.comments)
        literal = parse_example("B38")[0].expressions[0]
        self.assertIsInstance(literal, exp.Literal)
        self.assertEqual(literal.this, "1e2")


if __name__ == "__main__":
    unittest.main()
