"""Define analytical table shapes and daily keys from data contract v1.

DATASETS maps each connector dataset name to its table name, key, and schema.
An Arrow schema declares column order, types, and whether nulls are allowed.
These definitions do not validate source rows or write Parquet files.
"""

from dataclasses import dataclass
from types import MappingProxyType

import pyarrow as pa


# Precision 24 reserves 24 decimal digits in total. Scale 6 reserves six
# digits after the decimal point, leaving up to 18 digits before it.
# All three measurements use this type so their storage limits stay consistent.
MEASUREMENT_TYPE = pa.decimal128(24, 6)


# frozen=True prevents callers from replacing a definition's fields.
@dataclass(frozen=True)
class DatasetDefinition:
    """Define an analytical table name, its daily key, and its Arrow schema."""

    # table_name is the analytical name; the registry uses shorter route keys.
    table_name: str
    # These fields together identify one daily row within a dataset version.
    # Declaring a key does not check source rows for duplicates.
    key_fields: tuple[str, ...]
    schema: pa.Schema


def _schema(*entity_fields: str) -> pa.Schema:
    """Build the shared daily columns with the supplied entity IDs in order."""

    # *entity_fields collects positional names into a tuple.
    # No names means national; (facility, generator) means generator detail.
    # Explicit types keep optional columns typed even when every value is null.
    # date32 stores a calendar date without a time or timezone.
    fields = [pa.field("period", pa.date32(), nullable=False)]
    # IDs are strings so leading zeros and letter case remain intact.
    # nullable=False declares required columns; the parser checks source values.
    fields.extend(pa.field(name, pa.string(), nullable=False) for name in entity_fields)
    if entity_fields:
        # A facility label is optional descriptive text. It is not part of a key.
        fields.append(pa.field("facilityName", pa.string(), nullable=True))
    # Missing source percentages remain null. Capacity and outage are required.
    # This schema stores the reported percentage, not a calculated MW ratio.
    fields.extend([
        pa.field("capacity", MEASUREMENT_TYPE, nullable=False),
        pa.field("outage", MEASUREMENT_TYPE, nullable=False),
        pa.field("percentOutage", MEASUREMENT_TYPE, nullable=True),
    ])
    return pa.schema(fields)


# MappingProxyType prevents callers from adding or replacing registry entries.
# Each entry connects the source dataset name to one analytical table shape.
DATASETS = MappingProxyType({
    # National has one row per date, so period alone forms its daily key.
    "national": DatasetDefinition("national_outages", ("period",), _schema()),
    "facility": DatasetDefinition(
        "facility_outages", ("period", "facility"), _schema("facility"),
    ),
    # Generator IDs are unique within a facility, not across all facilities.
    "generator": DatasetDefinition(
        "generator_outages", ("period", "facility", "generator"),
        _schema("facility", "generator"),
    ),
})
