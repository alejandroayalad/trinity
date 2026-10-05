"""Produce bounded distinct source choices within the network-disabled runtime."""
from datetime import date
import json
from pathlib import Path
import pyarrow as pa
from datafusion import col, lit
from datafusion import functions as fn
from trinity.contracts.datasets import DATASETS
from trinity.contracts.queries import ChoiceOperation
from trinity.queries.runtime.engine import restricted_context, QueryExecutionError, MAX_RESPONSE_BYTES


def execute_choices(operation: ChoiceOperation, directory: Path):
    """Group inside DataFusion, then read at most page_size plus one choices.

    Latest non-null names are selected before literal case-insensitive search.
    IDs remain exact strings. Typed literals prevent search text from becoming
    SQL. Memory and execution time remain the external supervisor's limits.
    """
    try:
        operation = ChoiceOperation.from_bytes(operation.to_bytes())
        context = restricted_context(operation.dataset, directory)
        frame = context.table(DATASETS[operation.dataset].table_name)
        frame = frame.filter((col('period') >= lit(pa.scalar(date.fromisoformat(operation.start), pa.date32())))
                             & (col('period') <= lit(pa.scalar(date.fromisoformat(operation.end), pa.date32()))))
        field = 'facility' if operation.selection == 'facilities' else 'generator'
        if field == 'facility':
            # Filtering null names within the aggregate retains IDs whose names
            # are all missing. Same-day generator names use ID order as a tie break.
            order = [col('period').sort(ascending=False)]
            if operation.dataset == 'generator':
                order.append(col('generator').sort(ascending=True))
            frame = frame.aggregate([col('facility')], [fn.first_value(col('"facilityName"'),
                filter=col('"facilityName"').is_not_null(), order_by=order).alias('facilityName')])
            if operation.search is not None:
                search = fn.lower(lit(operation.search))
                frame = frame.filter((fn.strpos(fn.lower(col('facility')), search) > lit(0))
                                     | (fn.strpos(fn.lower(col('"facilityName"')), search) > lit(0)))
        else:
            frame = frame.filter(col('facility') == lit(operation.facility)).select('facility', 'generator').distinct()
        if operation.after_id is not None:
            frame = frame.filter(col(field) > lit(operation.after_id))
        frame = frame.sort(col(field).sort(ascending=True)).limit(operation.page_size + 1)
        items = []
        for record in frame.execute_stream():
            for item in record.to_pyarrow().to_pylist():
                if len(items) == operation.page_size:
                    return {'items': items, 'has_more': True}
                items.append(item)
                if len(json.dumps(items, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES - 1024:
                    raise QueryExecutionError('query_resource_limit')
        return {'items': items, 'has_more': False}
    except QueryExecutionError:
        raise
    except Exception:
        raise QueryExecutionError() from None
