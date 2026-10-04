"""SQL structure checks; passing one check does not authorize execution."""

import sqlglot
from sqlglot import Dialect, ErrorLevel, exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType


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
