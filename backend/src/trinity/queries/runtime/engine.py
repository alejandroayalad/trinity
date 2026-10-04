"""Execute verified operations against one trusted local Parquet directory.

This internal entrypoint requires external process/container supervision.
It is not an HTTP route or an in-process fallback for production requests.
"""

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path

import pyarrow as pa
from datafusion import SessionConfig, SessionContext, SQLOptions, RuntimeEnvBuilder

from trinity.contracts.datasets import DATASETS
from trinity.contracts.queries import ValidatedQuery
from trinity.queries.runtime.sql_policy import validate_query

MAX_ROWS = 1000
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class QueryExecutionError(RuntimeError):
    """Carry only a fixed safe failure code outside the query runtime."""
    def __init__(self, code="query_failed"):
        self.code = code
        super().__init__(code)


def _column_type(kind):
    if pa.types.is_decimal(kind): return "decimal"
    if pa.types.is_integer(kind): return "integer"
    if pa.types.is_boolean(kind): return "boolean"
    if pa.types.is_date(kind): return "date"
    if pa.types.is_timestamp(kind): return "timestamp"
    if (pa.types.is_string(kind) or pa.types.is_large_string(kind)
            or pa.types.is_string_view(kind) or pa.types.is_null(kind)): return "string"
    raise QueryExecutionError()


def _value(value):
    if value is None or type(value) in (str, bool): return value
    if type(value) is int: return str(value)
    if isinstance(value, Decimal) and value.is_finite(): return format(value, "f")
    if isinstance(value, (date, datetime)): return value.isoformat()
    raise QueryExecutionError()


def restricted_context(dataset, directory):
    """Register one canonical mounted table with spill and information schema disabled."""
    config = SessionConfig().with_information_schema(False)
    for key, value in (("datafusion.sql_parser.dialect", "PostgreSQL"),
                       ("datafusion.sql_parser.parse_float_as_decimal", "true"),
                       ("datafusion.sql_parser.enable_ident_normalization", "false")):
        config = config.set(key, value)
    runtime = RuntimeEnvBuilder().with_greedy_memory_pool(768 * 1024 * 1024).with_disk_manager_disabled()
    context = SessionContext(config, runtime)
    definition = DATASETS[dataset]
    context.register_parquet(definition.table_name, str(directory), schema=definition.schema)
    return context


def execute_local(query: ValidatedQuery, directory: Path) -> dict:
    """Revalidate policy before registering one trusted, staged dataset.

    Return a bounded result fragment, preserving exact numbers and duplicate
    labels. A supervisor must enforce wall time, memory and final-envelope size.
    """
    try:
        verified = validate_query(query.original_sql)
        if verified != query:
            raise QueryExecutionError()
        context = restricted_context(query.dataset, directory)
        options = SQLOptions().with_allow_ddl(False).with_allow_dml(False).with_allow_statements(False)
        frame = context.sql(query.operation, options=options)
        schema = frame.schema()
        if not 1 <= len(schema) <= 128 or len(schema) != len(query.columns):
            raise QueryExecutionError("query_resource_limit")
        columns = []
        for i, (field, public) in enumerate(zip(schema, query.columns)):
            if field.name != f"__trinity_c{i:03d}":
                raise QueryExecutionError()
            columns.append({"name": public.name, "type": _column_type(field.type),
                            "nullable": field.nullable, "unit": public.unit})
        result = {"columns": columns, "rows": [], "returned_rows": 0, "truncated": False, "diagnostics": []}
        size = len(json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode())
        for record in frame.limit(MAX_ROWS + 1).execute_stream():
            batch = record.to_pyarrow()
            for row_index in range(batch.num_rows):
                if len(result["rows"]) == MAX_ROWS:
                    result["truncated"] = True
                    break
                row = []
                for col_index, field in enumerate(schema):
                    value = batch.column(col_index)[row_index].as_py()
                    if value is None and not field.nullable:
                        raise QueryExecutionError()
                    row.append(_value(value))
                size += len(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode()) + 1
                if size > MAX_RESPONSE_BYTES - 1024:
                    raise QueryExecutionError("query_resource_limit")
                result["rows"].append(row)
            if result["truncated"]:
                break
        result["returned_rows"] = len(result["rows"])
        return result
    except QueryExecutionError:
        raise
    except Exception:
        raise QueryExecutionError() from None
