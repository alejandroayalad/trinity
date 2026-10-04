"""Execute typed preview predicates against the one authorized mounted table."""

from datetime import date
import json
from pathlib import Path

import pyarrow as pa
from datafusion import col, lit

from trinity.contracts.datasets import DATASETS
from trinity.contracts.queries import PreviewOperation
from trinity.queries.runtime.engine import (
    MAX_RESPONSE_BYTES, QueryExecutionError, _column_type, _value, restricted_context,
)


def execute_preview(operation: PreviewOperation, directory: Path) -> dict:
    """Return canonical columns and at most page_size rows plus a lookahead flag.

    Recheck the closed operation before registering files. Use typed literals,
    including for IDs that resemble SQL. External supervision owns the deadline,
    process memory limit and cleanup; this function owns no storage credentials.
    """
    try:
        operation = PreviewOperation.from_bytes(operation.to_bytes())
        definition = DATASETS[operation.dataset]
        context = restricted_context(operation.dataset, directory)
        frame = context.table(definition.table_name)
        period = col('period')
        predicate = ((period >= lit(pa.scalar(date.fromisoformat(operation.start), pa.date32())))
                     & (period <= lit(pa.scalar(date.fromisoformat(operation.end), pa.date32()))))
        for name in ('facility', 'generator'):
            value = getattr(operation, name)
            if value is not None:
                predicate = predicate & (col(name) == lit(value))
        if operation.after is not None:
            # (date, facility, generator) advances by the entire key. Equal dates
            # still admit the next facility or generator on that same date.
            greater = None
            equal = None
            for index, name in enumerate(definition.key_fields):
                value = operation.after[index]
                literal = lit(pa.scalar(date.fromisoformat(value), pa.date32())) if index == 0 else lit(value)
                part = col(name) > literal
                greater = part if greater is None else greater | (equal & part)
                same = col(name) == literal
                equal = same if equal is None else equal & same
            predicate = predicate & greater
        frame = frame.filter(predicate).sort(
            *(col(name).sort(ascending=True, nulls_first=False) for name in definition.key_fields)
        ).limit(operation.page_size + 1)
        columns = [{'name': field.name, 'type': _column_type(field.type), 'nullable': field.nullable,
                    'unit': 'MW' if field.name in ('capacity', 'outage') else
                            'percent' if field.name == 'percentOutage' else None}
                   for field in definition.schema]
        result = {'columns': columns, 'rows': [], 'has_more': False}
        size = len(json.dumps(result).encode())
        for record in frame.execute_stream():
            batch = record.to_pyarrow()
            for index in range(batch.num_rows):
                if len(result['rows']) == operation.page_size:
                    result['has_more'] = True
                    return result
                row = [_value(batch.column(i)[index].as_py()) for i in range(len(definition.schema))]
                size += len(json.dumps(row, ensure_ascii=True).encode()) + 1
                if size > MAX_RESPONSE_BYTES - 1024:
                    raise QueryExecutionError('query_resource_limit')
                result['rows'].append(row)
        return result
    except QueryExecutionError:
        raise
    except Exception:
        raise QueryExecutionError() from None
