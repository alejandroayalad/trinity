"""Add presentation metadata to the canonical analytical schemas."""

from types import MappingProxyType

import pyarrow as pa

from trinity.catalog.schemas import Column, Dataset, MetricDefinition
from trinity.contracts.datasets import DATASETS, MEASUREMENT_TYPE

PRESENTATION = MappingProxyType({
    "national": ("National outages", "One U.S. national observation per date.", ("start", "end")),
    "facility": ("Facility outages", "One facility observation per date; identifiers remain text.",
                 ("start", "end", "facility")),
    "generator": ("Generator outages", "One generator observation per facility and date; identifiers remain text.",
                  ("start", "end", "facility", "generator")),
})
UNITS = MappingProxyType({
    "period": None, "facility": None, "generator": None, "facilityName": None,
    "capacity": "MW", "outage": "MW", "percentOutage": "percent",
})


def _public_type(arrow_type):
    if pa.types.is_date32(arrow_type):
        return "date"
    if pa.types.is_string(arrow_type):
        return "string"
    if arrow_type == MEASUREMENT_TYPE:
        return "decimal"
    raise ValueError("Unsupported catalog column type")


def describe_dataset(internal_key: str) -> Dataset:
    """Build a fresh definition; missing metadata fails instead of omitting data."""
    definition = DATASETS[internal_key]
    label, description, filters = PRESENTATION[internal_key]
    return Dataset(
        key=definition.table_name, label=label, description=description,
        daily_key=list(definition.key_fields), available_filters=list(filters),
        columns=[Column(name=field.name, type=_public_type(field.type),
                        nullable=field.nullable, unit=UNITS[field.name])
                 for field in definition.schema],
    )


def describe_metric() -> MetricDefinition:
    """Describe the national metric separately from source percentOutage."""
    return MetricDefinition(
        key="offline_share_percent", label="National offline share", unit="percent",
        formula="100 × outage / capacity for the national row on one date; display rounded half-up.",
        null_reasons=["not_reported", "zero_capacity"], display_decimal_places=2,
    )
