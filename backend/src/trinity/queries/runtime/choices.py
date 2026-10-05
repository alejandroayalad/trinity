"""Compute distinct choices over the complete authorized observation range."""

from datetime import date
import json
from pathlib import Path

import pyarrow as pa
from datafusion import col, lit

from trinity.contracts.choices import ChoiceOperation, matches_search
from trinity.contracts.datasets import DATASETS
from trinity.queries.runtime.engine import MAX_RESPONSE_BYTES, QueryExecutionError, restricted_context


def execute_choices(operation: ChoiceOperation, directory: Path) -> dict:
    """Return a bounded page after reducing all matching dates to unique IDs.

    The fixed DataFusion window selects the latest non-null label per Plant.
    Conflicting labels on that date use binary ascending order. Search applies
    after that selection, so an obsolete label cannot produce a hidden match.
    The outer supervisor limits memory and time and owns container cleanup.
    """
    try:
        operation = ChoiceOperation.from_bytes(operation.to_bytes())
        context = restricted_context(operation.dataset, directory)
        frame = context.table(DATASETS[operation.dataset].table_name)
        period = col('period')
        frame = frame.filter(
            (period >= lit(pa.scalar(date.fromisoformat(operation.start), pa.date32())))
            & (period <= lit(pa.scalar(date.fromisoformat(operation.end), pa.date32()))))
        if operation.facility is not None:
            frame = frame.filter(col('facility') == lit(operation.facility))
        context.register_table('choice_observations', frame.into_view())
        # SQL text is constant. Request values entered only through typed literals
        # above or literal Python comparisons below; none can become SQL syntax.
        if operation.choice == 'facilities':
            choices = context.sql('''SELECT facility, "facilityName" FROM (
                SELECT facility, "facilityName", ROW_NUMBER() OVER (
                    PARTITION BY facility ORDER BY ("facilityName" IS NULL) ASC,
                    period DESC, "facilityName" ASC NULLS LAST) AS choice_rank
                FROM choice_observations) WHERE choice_rank = 1 ORDER BY facility''')
            key = 'facility'
        else:
            choices = context.sql('''SELECT DISTINCT facility, generator
                FROM choice_observations ORDER BY generator''')
            key = 'generator'
        items = []
        output_bytes = 0
        for record in choices.execute_stream():
            for item in record.to_pyarrow().to_pylist():
                identifier = item[key]
                if operation.after is not None and identifier.encode('utf-8') <= operation.after.encode('utf-8'):
                    continue
                if not matches_search(identifier, item.get('facilityName'), operation.search):
                    continue
                if len(items) == operation.page_size:
                    return {'items': items, 'has_more': True}
                output_bytes += len(json.dumps(item, ensure_ascii=True).encode('utf-8'))
                if output_bytes > MAX_RESPONSE_BYTES - 1024:
                    raise QueryExecutionError('query_resource_limit')
                items.append(item)
        return {'items': items, 'has_more': False}
    except QueryExecutionError:
        raise
    except Exception:
        raise QueryExecutionError() from None
