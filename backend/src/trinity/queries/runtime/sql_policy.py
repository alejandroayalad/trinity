"""SQL structure checks; passing one check does not authorize execution."""

import sqlglot
from sqlglot import Dialect, ErrorLevel, exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType
from sqlglot.dialects.postgres import Postgres


class SQLValidationError(ValueError):
    """Report a SQL validation failure without including the submitted SQL."""


def validate_single_statement(sql: str) -> exp.Select:
    """Parse the whole input and require exactly one nonempty SELECT root.

    Raise SQLValidationError for parse failures or a different root/count.
    Allow one terminal semicolon followed only by whitespace or comments.
    This does not check tables, clauses, functions or execution permissions.
    """
    try:
        tokens = Dialect.get_or_raise("postgres").tokenize(sql)
        semicolons = [i for i, token in enumerate(tokens)
                      if token.token_type == TokenType.SEMICOLON]
        if semicolons and semicolons != [len(tokens) - 1]:
            raise SQLValidationError("Only one terminal semicolon is allowed.")

        parsed = sqlglot.parse(
            sql, read="postgres", error_level=ErrorLevel.IMMEDIATE,
            max_errors=1, max_nodes=4096,
        )
    except (ParseError, TokenError):
        raise SQLValidationError("Invalid SQL syntax.") from None

    trailing_comments = []
    # SQLGlot puts comments after the verified terminator on a separate node.
    if (semicolons and len(parsed) == 2
            and isinstance(parsed[1], exp.Semicolon)
            and not parsed[1].args and parsed[1].comments):
        trailing_comments = parsed.pop().comments

    if len(parsed) != 1:
        raise SQLValidationError("Exactly one SQL statement is required.")

    statement = parsed[0]
    if statement is None:
        raise SQLValidationError("A SQL statement is required.")
    if not isinstance(statement, exp.Select):
        raise SQLValidationError("The statement must be a SELECT.")

    statement.add_comments(trailing_comments)
    return statement


# Each class has its own reviewed argument shape. Unknown populated fields fail.
_ARGUMENTS = {
    exp.Select: {"expressions", "from_", "where", "group", "order", "limit"},
    exp.From: {"this"}, exp.Table: {"this", "alias"}, exp.TableAlias: {"this"},
    exp.Identifier: {"this", "quoted"}, exp.Column: {"this", "table"},
    exp.Alias: {"this", "alias"}, exp.Star: set(),
    exp.Literal: {"this", "is_string"}, exp.Boolean: {"this"}, exp.Null: set(),
    exp.Cast: {"this", "to"}, exp.DataType: {"this", "nested"},
    exp.Where: {"this"}, exp.Group: {"expressions"}, exp.Order: {"expressions"},
    exp.Ordered: {"this", "desc", "nulls_first"}, exp.Limit: {"expression"},
    exp.Paren: {"this"}, exp.Neg: {"this"}, exp.Not: {"this"},
    exp.Add: {"this", "expression"}, exp.Sub: {"this", "expression"},
    exp.Mul: {"this", "expression"}, exp.Div: {"this", "expression", "typed", "safe"},
    exp.EQ: {"this", "expression"}, exp.NEQ: {"this", "expression"},
    exp.GT: {"this", "expression"}, exp.GTE: {"this", "expression"},
    exp.LT: {"this", "expression"}, exp.LTE: {"this", "expression"},
    exp.And: {"this", "expression"}, exp.Or: {"this", "expression"},
    exp.Is: {"this", "expression", "negate"}, exp.Between: {"this", "low", "high"},
    exp.In: {"this", "expressions"}, exp.Case: {"ifs", "default"}, exp.If: {"this", "true"},
    exp.Count: {"this", "expressions", "big_int"}, exp.Sum: {"this"}, exp.Avg: {"this"},
    exp.Min: {"this", "expressions"}, exp.Max: {"this", "expressions"},
    exp.Round: {"this", "decimals"}, exp.Coalesce: {"this", "expressions"},
    exp.Nullif: {"this", "expression"},
}
_FUNCTIONS = {exp.Count: "COUNT", exp.Sum: "SUM", exp.Avg: "AVG", exp.Min: "MIN",
              exp.Max: "MAX", exp.Round: "ROUND", exp.Coalesce: "COALESCE", exp.Nullif: "NULLIF"}
_AGGREGATES = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
_TOKEN_NAMES = set("SELECT VAR COMMA FROM ORDER_BY LIMIT NUMBER IDENTIFIER WHERE EQ STRING AND DOT STAR "
                   "ALIAS GTE LTE OR NOT L_PAREN R_PAREN NEQ DASH BETWEEN IN IS NULL DATE PLUS SLASH "
                   "CASE WHEN GT THEN ELSE END LT GROUP_BY DESC FIRST ASC SEMICOLON TRUE FALSE".split())


def _deny() -> None:
    raise SQLValidationError("SQL is outside the supported grammar.")


def _compatible(types):
    concrete = set(types) - {"null"}
    if len(concrete) > 1:
        _deny()
    return next(iter(concrete), "null")


class _Generator(Postgres.Generator):
    TRANSFORMS = {**Postgres.Generator.TRANSFORMS, exp.Round: lambda self, e: self.round_sql(e)}
    def round_sql(self, expression):
        args = [self.sql(expression, "this")]
        if expression.args.get("decimals") is not None:
            args.append(self.sql(expression, "decimals"))
        return "ROUND(" + ", ".join(args) + ")"

    def ordered_sql(self, expression):
        direction = "DESC" if expression.args["desc"] else "ASC"
        nulls = "FIRST" if expression.args["nulls_first"] else "LAST"
        return f"{self.sql(expression, 'this')} {direction} NULLS {nulls}"


class _Policy:
    def __init__(self, sql, *, internal=False):
        from trinity.contracts.datasets import DATASETS
        self.sql, self.internal = sql, internal
        self.tokens = Dialect.get_or_raise("postgres").tokenize(sql)
        self.positions = {t.start: i for i, t in enumerate(self.tokens)}
        if (not self.tokens or self.tokens[0].token_type != TokenType.SELECT
                or any(t.token_type.name not in _TOKEN_NAMES for t in self.tokens)):
            _deny()
        self.tree = validate_single_statement(sql)
        for node in self.tree.walk():
            allowed = _ARGUMENTS.get(type(node))
            if allowed is None or any(k not in allowed and v is not None and v != []
                                      for k, v in node.args.items()):
                _deny()
            if any(c.lstrip().startswith("+") for c in node.comments or []):
                _deny()
        if any(t.token_type.name not in _TOKEN_NAMES for t in self.tokens):
            _deny()
        source = self.tree.args.get("from_")
        tables = list(self.tree.find_all(exp.Table))
        if (not isinstance(source, exp.From) or type(source.this) is not exp.Table
                or len(tables) != 1 or type(source.this.this) is not exp.Identifier):
            _deny()
        self.table = source.this
        self.dataset = next((k for k, v in DATASETS.items() if v.table_name == self.table.name), None)
        if self.dataset is None:
            _deny()
        self.definition = DATASETS[self.dataset]
        alias = self.table.args.get("alias")
        if alias is not None and (type(alias) is not exp.TableAlias or type(alias.this) is not exp.Identifier):
            _deny()
        self.qualifiers = {self.table.name, self.table.alias_or_name}
        self.types = {f.name: ("number" if str(f.type).startswith("decimal") else
                              "date" if str(f.type) == "date32[day]" else "string")
                      for f in self.definition.schema}
        for node in self.tree.find_all(exp.Identifier):
            if not 1 <= len(node.this) <= 128 or any(ord(c) < 32 for c in node.this):
                _deny()

    def _source_token(self, node):
        index = self.positions.get(node.meta.get("start"))
        if index is None:
            _deny()
        return index

    def column(self, node):
        if (type(node) is not exp.Column or type(node.this) is not exp.Identifier
                or node.name not in self.types or node.table and node.table not in self.qualifiers):
            _deny()
        return self.types[node.name]

    def scalar(self, node, *, aggregates=True, nested=False):
        from datetime import date
        import re
        kind = type(node)
        child = lambda n: self.scalar(n, aggregates=aggregates, nested=nested)
        if kind is exp.Column:
            return self.column(node)
        if kind is exp.Literal:
            if node.is_string:
                return "string"
            if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", node.this):
                _deny()
            return "number"
        if kind is exp.Null:
            return "null"
        if kind is exp.Boolean:
            return "boolean"
        if kind is exp.Paren:
            return child(node.this)
        if kind is exp.Cast:
            if (type(node.this) is not exp.Literal or not node.this.is_string
                    or node.args["to"].this != exp.DataType.Type.DATE or node.args["to"].args.get("nested")):
                _deny()
            index = self._source_token(node.this)
            if not self.internal and (index == 0 or self.tokens[index - 1].token_type != TokenType.DATE):
                _deny()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", node.this.this):
                _deny()
            try:
                date.fromisoformat(node.this.this)
            except ValueError:
                _deny()
            return "date"
        if kind in (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Neg):
            if kind is exp.Div and (node.args.get("safe") is not False or node.args.get("typed") is not True):
                _deny()
            values = [child(node.this)] + ([] if kind is exp.Neg else [child(node.expression)])
            if any(t not in ("number", "null") for t in values):
                _deny()
            return "number"
        if kind in (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE):
            _compatible([child(node.this), child(node.expression)])
            return "boolean"
        if kind in (exp.And, exp.Or, exp.Not):
            values = [child(node.this)] + ([] if kind is exp.Not else [child(node.expression)])
            if any(t not in ("boolean", "null") for t in values):
                _deny()
            return "boolean"
        if kind is exp.Is:
            child(node.this)
            if type(node.expression) is not exp.Null:
                _deny()
            return "boolean"
        if kind is exp.Between:
            _compatible([child(node.this), child(node.args["low"]), child(node.args["high"])])
            return "boolean"
        if kind is exp.In:
            if not node.expressions:
                _deny()
            values = [child(node.this)]
            for item in node.expressions:
                literal = item.this if type(item) is exp.Neg else item
                if type(literal) not in (exp.Literal, exp.Boolean, exp.Null, exp.Cast):
                    _deny()
                values.append(child(item))
            _compatible(values)
            return "boolean"
        if kind is exp.Case:
            if not node.args.get("ifs"):
                _deny()
            values = []
            for arm in node.args["ifs"]:
                if type(arm) is not exp.If or child(arm.this) not in ("boolean", "null"):
                    _deny()
                values.append(child(arm.args["true"]))
            if node.args.get("default") is not None:
                values.append(child(node.args["default"]))
            return _compatible(values)
        if kind in _FUNCTIONS:
            index = self._source_token(node)
            if self.tokens[index].text.upper() != _FUNCTIONS[kind]:
                _deny()
            if kind in _AGGREGATES:
                if not aggregates or nested or node.args.get("expressions"):
                    _deny()
                if kind is exp.Count and node.args.get("big_int") is not True:
                    _deny()
                if kind is exp.Count and type(node.this) is exp.Star:
                    return "number"
                value = self.scalar(node.this, aggregates=aggregates, nested=True)
                if kind in (exp.Sum, exp.Avg) and value not in ("number", "null"):
                    _deny()
                return "number" if kind in (exp.Sum, exp.Avg, exp.Count) else value
            if kind is exp.Round:
                if child(node.this) not in ("number", "null"):
                    _deny()
                scale = node.args.get("decimals")
                if scale is not None:
                    value = scale.this if type(scale) is exp.Neg else scale
                    if type(value) is not exp.Literal or value.is_string or not value.this.isdigit():
                        _deny()
                    if int(value.this) > 18:
                        _deny()
                return "number"
            if kind is exp.Coalesce:
                if not node.expressions:
                    _deny()
                return _compatible([child(node.this), *[child(n) for n in node.expressions]])
            return _compatible([child(node.this), child(node.expression)])
        _deny()

    def normalize(self):
        from collections import Counter
        from trinity.contracts.queries import OutputColumn
        projections, columns, aliases = [], [], []
        expression_number = 0
        for projection in self.tree.expressions:
            alias = projection.alias if type(projection) is exp.Alias else None
            value = projection.this if alias is not None else projection
            if alias is not None:
                alias_node = projection.args["alias"]
                index = self._source_token(alias_node)
                if index == 0 or self.tokens[index - 1].token_type != TokenType.ALIAS:
                    _deny()
            if type(value) is exp.Star or (type(value) is exp.Column and type(value.this) is exp.Star):
                if alias is not None or type(value) is exp.Column and value.table not in self.qualifiers:
                    _deny()
                values = [exp.column(name, quoted=True) for name in self.types]
            else:
                self.scalar(value)
                values = [value]
            for item in values:
                direct = type(item) is exp.Column
                if not direct and alias is None:
                    expression_number += 1
                label = alias or (item.name if direct else f"expression_{expression_number}")
                unit = ("MW" if item.name in ("capacity", "outage") else
                        "percent" if item.name == "percentOutage" else None) if direct else None
                projections.append(item)
                columns.append(OutputColumn(label, unit))
                aliases.append(alias)
        if not 1 <= len(projections) <= 128:
            _deny()
        where = self.tree.args.get("where")
        if where is not None and self.scalar(where.this, aggregates=False) not in ("boolean", "null"):
            _deny()
        group = self.tree.args.get("group")
        grouped = set()
        if group is not None:
            if not group.expressions:
                _deny()
            for col in group.expressions:
                self.column(col)
                grouped.add(col.name)
        aggregate_query = group is not None or any(isinstance(n, _AGGREGATES)
                            for value in projections for n in value.walk())
        def grouped_expression(value):
            if not aggregate_query:
                return
            def visit(n):
                if isinstance(n, _AGGREGATES):
                    return
                if type(n) is exp.Column and n.name not in grouped:
                    _deny()
                for ch in n.iter_expressions():
                    visit(ch)
            visit(value)
        for value in projections:
            grouped_expression(value)
        counts = Counter(a for a in aliases if a is not None)
        order = self.tree.args.get("order")
        if order is not None:
            for ordered in order.expressions:
                col = ordered.this
                if type(col) is not exp.Column or type(col.this) is not exp.Identifier:
                    _deny()
                index = self._source_token(col.this)
                end = index + 1
                while end < len(self.tokens) and self.tokens[end].token_type.name not in ("COMMA", "LIMIT", "SEMICOLON"):
                    end += 1
                explicit_nulls = any(t.text.upper() == "NULLS" for t in self.tokens[index + 1:end])
                if not explicit_nulls:
                    ordered.set("nulls_first", False)
                ordered.set("desc", bool(ordered.args.get("desc")))
                if not col.table and col.name in counts:
                    if counts[col.name] != 1:
                        _deny()
                    pos = aliases.index(col.name)
                    ordered.set("this", exp.column(f"__trinity_c{pos:03d}", quoted=True))
                else:
                    self.column(col)
                    grouped_expression(col)
        limit = self.tree.args.get("limit")
        if limit is not None:
            n = limit.expression
            if type(n) is not exp.Literal or n.is_string or not n.this.isdigit():
                _deny()
        self.tree.set("expressions", [exp.alias_(value.copy(), f"__trinity_c{i:03d}", quoted=True)
                                       for i, value in enumerate(projections)])
        for node in self.tree.walk():
            node.comments = None
            if type(node) is exp.Column and node.table:
                node.set("table", exp.to_identifier(self.table.alias_or_name, quoted=True))
            if type(node) is exp.Identifier:
                node.set("quoted", True)
        return _Generator(dialect=Postgres()).generate(self.tree), tuple(columns)


def validate_query(sql: str):
    """Validate the complete D01 policy and return a normalized closed message.

    No file access, SQL execution or caller authorization occurs here.
    The service must run this function in its bounded policy subprocess.
    """
    from trinity.contracts.queries import ValidatedQuery
    try:
        if type(sql) is not str or not 1 <= len(sql.encode("utf-8")) <= 16384:
            _deny()
        tokens = Dialect.get_or_raise("postgres").tokenize(sql)
        if len(tokens) > 4096:
            _deny()
        depth = 0
        for token in tokens:
            depth += (token.token_type == TokenType.L_PAREN) - (token.token_type == TokenType.R_PAREN)
            if depth > 64 or depth < 0:
                _deny()
        policy = _Policy(sql)
        if sum(1 for _ in policy.tree.walk()) > 4096 or any(n.depth > 64 for n in policy.tree.walk()):
            _deny()
        operation, columns = policy.normalize()
        roundtrip = _Policy(operation, internal=True)
        regenerated, internal_columns = roundtrip.normalize()
        if (regenerated != operation or roundtrip.dataset != policy.dataset
                or [c.unit for c in internal_columns] != [c.unit for c in columns]):
            _deny()
        result = ValidatedQuery(sql, policy.dataset, operation, columns)
        if len(result.to_bytes()) > 256 * 1024:
            _deny()
        return result
    except SQLValidationError:
        raise
    except (ParseError, TokenError, ValueError, TypeError, KeyError, AttributeError, RecursionError, UnicodeError):
        _deny()
