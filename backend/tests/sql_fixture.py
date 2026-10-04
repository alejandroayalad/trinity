"""Build synthetic canonical tables for SQL compatibility and staging tests."""

from datetime import date, timedelta
from decimal import Decimal
import pyarrow as pa
import pyarrow.parquet as pq

from trinity.contracts.datasets import DATASETS


def write_table(directory, dataset='national', *, count=3, values=None):
    """Write one typed file, with an explicit null percentage in the first row."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(count):
        row = {"period": date(2025, 1, 1) + timedelta(days=i),
               "capacity": Decimal('100.000000'), "outage": Decimal(str(i + 1)),
               "percentOutage": None if i == 0 else Decimal('1.000001')}
        if dataset != 'national': row.update(facility='46', facilityName='Synthetic')
        if dataset == 'generator': row['generator'] = '1'
        if values: row.update(values[i % len(values)])
        rows.append(row)
    table = pa.Table.from_pylist(rows, schema=DATASETS[dataset].schema)
    path = directory / 'part-000000.parquet'
    pq.write_table(table, path)
    return path
