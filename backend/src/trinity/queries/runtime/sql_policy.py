"""SQL structure checks; passing one check does not authorize execution."""

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.errors import ParseError, TokenError


class SQLValidationError(ValueError):
    """Report a SQL validation failure without including the submitted SQL."""


def validate_single_statement(sql: str) -> exp.Select:
    """Parse the whole input and require exactly one nonempty SELECT root.

    Raise SQLValidationError for parse failures or a different root/count.
    This does not check tables, clauses, functions or execution permissions.
    """
    try:
        parsed = sqlglot.parse(
            sql, read="postgres", error_level=ErrorLevel.IMMEDIATE,
            max_errors=1, max_nodes=4096,
        )
    except (ParseError, TokenError):
        raise SQLValidationError("Invalid SQL syntax.") from None

    if len(parsed) != 1:
        raise SQLValidationError("Exactly one SQL statement is required.")

    statement = parsed[0]
    if statement is None:
        raise SQLValidationError("A SQL statement is required.")
    if not isinstance(statement, exp.Select):
        raise SQLValidationError("The statement must be a SELECT.")

    return statement
