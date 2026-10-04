"""Convert sanitized EIA text into Python values for the analytical schemas.

Use normalize_row as the entry point. This module parses one row at a time.
It does not fetch source data, write files, or approve a candidate.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import re
from typing import Any

from trinity.contracts.datasets import DATASETS


# Require ASCII digits and fixed widths: YYYY-MM-DD.
# The date parser below checks whether that date exists in the calendar.
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Allow an optional sign, integer digits, and an optional decimal fraction.
# Reject exponents, separators, spaces, and special values such as NaN.
_DECIMAL_TEXT = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
# This type alias lists the possible output types. None represents a null.
# Type hints describe values; the functions below perform the actual checks.
ParsedValue = date | str | Decimal | None


class NormalizationError(ValueError):
    """Report a field and error code without including its source value."""

    def __init__(self, code: str, field_name: str) -> None:
        # Callers can inspect these attributes without parsing the message.
        # Keep the rejected source value in caller-owned evidence, not errors.
        self.code = code
        self.field_name = field_name
        super().__init__(f"Invalid source field {field_name}: {code}.")


# A dataclass creates the constructor from the declared fields.
# frozen=True prevents field replacement, but values remains a mutable dict.
@dataclass(frozen=True)
class NormalizedRow:
    """Hold analytical values and observation codes, not a readiness decision."""

    # repr=False hides values when Python displays this result object.
    # It does not sanitize values or prevent direct access to the dictionary.
    values: dict[str, ParsedValue] = field(repr=False)
    diagnostic_codes: tuple[str, ...]


def _required_text(value: Any, field_name: str) -> str:
    """Reject missing, blank, or non-string input without converting it."""

    # Source IDs and measurements must arrive as text. Converting a numeric
    # ID to text cannot recover leading zeros that the source already lost.
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError("required_text", field_name)
    # Use stripping only to detect blanks. Preserve source IDs and labels.
    return value


def _date(value: Any) -> date:
    """Require YYYY-MM-DD text and return a valid calendar date."""

    text = _required_text(value, "period")
    # fullmatch checks the entire string, including unwanted trailing text.
    if not _DATE_TEXT.fullmatch(text):
        raise NormalizationError("invalid_date", "period")
    try:
        # Correct spelling does not prove calendar validity.
        # For example, 2024-02-29 exists, but 2025-02-29 does not.
        return date.fromisoformat(text)
    except ValueError:
        # from None suppresses the original exception in the displayed chain.
        # Report our field/code message instead of the date parser's message.
        raise NormalizationError("invalid_date", "period") from None


def _decimal(value: Any, field_name: str) -> Decimal:
    """Parse exact measurement text that fits DECIMAL(24,6) without rounding."""

    text = _required_text(value, field_name)
    if not _DECIMAL_TEXT.fullmatch(text):
        raise NormalizationError("invalid_decimal", field_name)
    # Split a copy for digit counting. The underscore discards the separator.
    # Without a decimal point, partition returns an empty fractional part.
    integral, _, fractional = text.lstrip("+-").partition(".")
    # DECIMAL(24,6) allows 18 integer digits and six fractional digits.
    # Ignore insignificant zeros only for this fit check. Never round to fit.
    if len(integral.lstrip("0")) > 18:
        raise NormalizationError("decimal_overflow", field_name)
    # "863.4000000" fits: its extra fractional zeros do not change the value.
    # "863.4000001" fails: removing the seventh digit would change the value.
    if len(fractional.rstrip("0")) > 6:
        raise NormalizationError("decimal_scale", field_name)
    # Decimal parses text exactly. A float conversion can lose precision.
    # Direct construction also avoids the precision limit for Decimal arithmetic.
    # Preserve trailing zeros here; the caller still retains the original text.
    result = Decimal(text)
    # Keep signed outage and unusual percentages for separate diagnostic checks.
    if field_name == "capacity" and result < 0:
        raise NormalizationError("negative_capacity", field_name)
    return result


def _optional_text(value: Any, field_name: str) -> str | None:
    """Return None for absent or blank text; reject other non-string values."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise NormalizationError("invalid_text", field_name)
    # Preserve nonblank text as supplied, including spaces around a label.
    return value if value.strip() else None


def _unit(row: dict[str, Any], field_name: str, expected: str) -> None:
    """Require the exact source unit label; do not convert measurements."""

    # For capacity, read capacity-units. A missing key gives None and fails.
    # A value in kilowatts cannot be treated as megawatts without conversion.
    if row.get(f"{field_name}-units") != expected:
        raise NormalizationError("invalid_units", f"{field_name}-units")


def normalize_row(dataset: str, row: dict[str, Any]) -> NormalizedRow:
    """Parse one sanitized EIA row into analytical values and observation codes.

    The connector must sanitize the input first. Parse dates and identifiers.
    Check units. Convert measurement text to exact Decimal values.
    This function does not read or write files or make network requests.
    The caller retains the unchanged source row as evidence, even on failure.
    The result contains only schema columns. D01 marks a missing facility label;
    D02 marks a missing source percentage. These are not a complete warning set.

    Raise NormalizationError for an unknown dataset or invalid source fields.
    Values must fit the schema without rounding or unit conversion.
    This function does not check the date window, duplicate keys, coverage,
    or totals across datasets. It does not decide publication readiness.
    """
    # Validate the container types before dictionary lookups or field access.
    # Short-circuit evaluation prevents a lookup for a non-string dataset.
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise NormalizationError("unknown_dataset", "dataset")
    if not isinstance(row, dict):
        raise NormalizationError("invalid_row", "row")
    definition = DATASETS[dataset]
    # Build a separate dictionary. Unknown source fields stay in row as evidence.
    # Every dataset uses period as the first part of its daily key.
    values: dict[str, ParsedValue] = {"period": _date(row.get("period"))}
    diagnostics: list[str] = []
    # [1:] skips period, which is already parsed. National has no entity ID.
    # Facility needs facility; generator needs both facility and generator.
    for name in definition.key_fields[1:]:
        values[name] = _required_text(row.get(name), name)
    # Only facility and generator rows have a facility label.
    # A missing label produces D01 and a null, rather than rejecting the row.
    if "facilityName" in definition.schema.names:
        values["facilityName"] = _optional_text(row.get("facilityName"), "facilityName")
        if values["facilityName"] is None:
            diagnostics.append("D01")
    # Both MW measurements are required. Check units before parsing each value.
    # An invalid measurement raises immediately; no partial result is returned.
    for name in ("capacity", "outage"):
        _unit(row, name, "megawatts")
        values[name] = _decimal(row.get(name), name)
    percent = _optional_text(row.get("percentOutage"), "percentOutage")
    if percent is None:
        # A missing source percentage stays unknown, even when MW values exist.
        values["percentOutage"] = None
        diagnostics.append("D02")
    else:
        # Require percentage units only when a source percentage is present.
        # Preserve the reported percentage; do not recalculate it from MW here.
        _unit(row, "percentOutage", "percent")
        values["percentOutage"] = _decimal(percent, "percentOutage")
    # A tuple fixes the collected code sequence. It does not make this row ready
    # for publication; checks across rows and full diagnostics are separate work.
    return NormalizedRow(values, tuple(diagnostics))
