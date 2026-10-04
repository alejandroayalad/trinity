"""Check analytical schemas and exact parsing with synthetic source rows.

Schema tests check the declared table shapes and in-memory Arrow conversion.
Parser tests check accepted values, rejected values, and source preservation.
The connector test supplies a mock HTTP response; no live EIA request runs.
These tests do not write Parquet files or check publication readiness.
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest

import httpx
import pyarrow as pa

from trinity.config import EIASettings
from trinity.connector.client import EIAClient
from trinity.connector.normalize import NormalizationError, normalize_row
from trinity.contracts.datasets import DATASETS


def source_row(dataset: str = "national") -> dict:
    """Return a fresh synthetic EIA row for the requested dataset."""

    # Each call returns a new dictionary so one test cannot alter another input.
    # Extra decimal zeros, leading ID zeros, and label spaces expose data loss.
    row = {
        "period": "2026-10-01", "capacity": "100.0000000", "outage": "12.5000000",
        "percentOutage": "12.5", "capacity-units": "megawatts",
        "outage-units": "megawatts", "percentOutage-units": "percent",
    }
    if dataset != "national":
        row.update(facility="001a", facilityName=" Synthetic plant ")
    if dataset == "generator":
        row["generator"] = "01B"
    return row


class DatasetSchemaTests(unittest.TestCase):
    """Check the contract at each row level: national, facility, and generator."""

    def test_exact_fields_keys_and_nullability_at_each_grain(self) -> None:
        # Keep the expected contract separate from the schema builder.
        # Deriving these expectations from DATASETS would hide schema mistakes.
        expected = {
            "national": (["period", "capacity", "outage", "percentOutage"], ("period",)),
            "facility": (
                ["period", "facility", "facilityName", "capacity", "outage", "percentOutage"],
                ("period", "facility"),
            ),
            "generator": (
                ["period", "facility", "generator", "facilityName", "capacity", "outage", "percentOutage"],
                ("period", "facility", "generator"),
            ),
        }
        self.assertEqual(set(DATASETS), set(expected))
        for key, (names, keys) in expected.items():
            # subTest identifies the failing dataset while checking all cases.
            with self.subTest(dataset=key):
                definition = DATASETS[key]
                self.assertEqual(definition.table_name, f"{key}_outages")
                self.assertEqual(definition.key_fields, keys)
                self.assertEqual(definition.schema.names, names)
                for column in definition.schema:
                    self.assertEqual(column.nullable, column.name in {"facilityName", "percentOutage"})
                    expected_type = (
                        pa.date32() if column.name == "period" else
                        pa.decimal128(24, 6) if column.name in {"capacity", "outage", "percentOutage"}
                        else pa.string()
                    )
                    self.assertEqual(column.type, expected_type)

    def test_all_null_optional_columns_remain_typed_in_arrow(self) -> None:
        for dataset, definition in DATASETS.items():
            with self.subTest(dataset=dataset):
                row = source_row(dataset)
                row.pop("percentOutage")
                row.pop("facilityName", None)
                result = normalize_row(dataset, row)
                # An explicit schema must keep the declared types even when
                # no optional value is available for Arrow to infer a type.
                table = pa.Table.from_pylist([result.values], schema=definition.schema)
                self.assertTrue(table.schema.equals(definition.schema))
                for name in ("percentOutage", "facilityName"):
                    if name in definition.schema.names:
                        self.assertEqual(table[name].null_count, 1)
                self.assertEqual(table.to_pylist()[0]["capacity"], Decimal("100.0000000"))


class NormalizationTests(unittest.TestCase):
    """Check one-row parsing rules without storage or network access."""

    def test_dates_identifiers_and_labels_are_preserved(self) -> None:
        # A valid leap day tests calendar parsing. ID spaces and leading zeros
        # must survive because identifiers are source text, not numbers.
        row = source_row("generator")
        row.update(period="2024-02-29", facility=" 001a ")
        result = normalize_row("generator", row)
        self.assertEqual(result.values["period"], date(2024, 2, 29))
        self.assertEqual(result.values["facility"], " 001a ")
        self.assertEqual(result.values["generator"], "01B")
        self.assertEqual(result.values["facilityName"], " Synthetic plant ")
        self.assertEqual(result.diagnostic_codes, ())

    def test_noncanonical_or_impossible_dates_fail(self) -> None:
        # Cover invalid calendars as well as text outside YYYY-MM-DD.
        # The final sample uses full-width digits instead of ASCII digits.
        for value in ("2025-02-29", "2026-2-01", "20261001", "2026-10-01T00:00:00Z",
                      " 2026-10-01", "2026-10-01\n", "0000-01-01", "２０２６-10-01"):
            with self.subTest(value=value):
                row = source_row(); row["period"] = value
                with self.assertRaises(NormalizationError) as caught:
                    normalize_row("national", row)
                self.assertEqual(caught.exception.code, "invalid_date")

    def test_required_values_are_never_coerced(self) -> None:
        # Numeric JSON values and booleans must fail, even if str() could
        # convert them. Missing keys and explicit nulls must also fail.
        for name in ("period", "facility", "generator", "capacity", "outage"):
            for value in (None, "", " \t\n", 0, 1.5, True, [], {}):
                with self.subTest(field=name, value=value):
                    row = source_row("generator"); row[name] = value
                    with self.assertRaises(NormalizationError) as caught:
                        normalize_row("generator", row)
                    self.assertEqual(caught.exception.field_name, name)
            row = source_row("generator"); del row[name]
            with self.subTest(missing=name), self.assertRaises(NormalizationError):
                normalize_row("generator", row)

    def test_optional_blanks_and_absence_return_null_and_observation_codes(self) -> None:
        for value in (None, "", " \t\n"):
            row = source_row("facility")
            row.update(facilityName=value, percentOutage=value)
            # A missing percentage does not need a unit label.
            # D02 records its absence without inventing a percentage value.
            row.pop("percentOutage-units")
            result = normalize_row("facility", row)
            self.assertIsNone(result.values["facilityName"])
            self.assertIsNone(result.values["percentOutage"])
            self.assertEqual(result.diagnostic_codes, ("D01", "D02"))
        row.pop("facilityName"); row.pop("percentOutage")
        self.assertEqual(normalize_row("facility", row).diagnostic_codes, ("D01", "D02"))
        national = source_row(); national.pop("percentOutage")
        self.assertEqual(normalize_row("national", national).diagnostic_codes, ("D02",))

    def test_nonstring_optional_values_fail(self) -> None:
        # Optional permits absence; it does not permit arbitrary value types.
        for name in ("facilityName", "percentOutage"):
            for value in (1, 1.2, False, [], {}):
                row = source_row("facility"); row[name] = value
                with self.subTest(field=name, value=value), self.assertRaises(NormalizationError):
                    normalize_row("facility", row)

    def test_live_facility_leading_decimal_percentage_is_exact(self) -> None:
        row = source_row("facility")
        row.update(period="2026-10-02", facility="869", capacity="1881.2",
                   outage="9.412", percentOutage=".5")
        before = deepcopy(row)
        result = normalize_row("facility", row)
        self.assertEqual(result.values["percentOutage"], Decimal("0.5"))
        self.assertEqual(result.diagnostic_codes, ())
        self.assertEqual(row, before)

    def test_leading_decimal_measurements_preserve_sign_and_scale_limits(self) -> None:
        for field in ("capacity", "outage", "percentOutage"):
            for text in (".5", "+.5", ".000001000", "-.0"):
                with self.subTest(field=field, value=text):
                    row = source_row(); row[field] = text
                    self.assertEqual(normalize_row("national", row).values[field], Decimal(text))
            row = source_row(); row[field] = ".0000001"
            with self.assertRaises(NormalizationError) as caught:
                normalize_row("national", row)
            self.assertEqual(caught.exception.code, "decimal_scale")
        row = source_row(); row["capacity"] = "-.5"
        with self.assertRaises(NormalizationError) as caught:
            normalize_row("national", row)
        self.assertEqual(caught.exception.code, "negative_capacity")
        row = source_row(); row.update(outage="-.5", percentOutage="-.5")
        result = normalize_row("national", row)
        self.assertEqual(result.values["outage"], Decimal("-0.5"))
        self.assertEqual(result.values["percentOutage"], Decimal("-0.5"))

    def test_trailing_zeros_survive_parsing_even_with_low_decimal_precision(self) -> None:
        samples = (
            "863.4000000", "999999999999999999.9999990000", "0.0000010000",
            "0.000000000", "-0.0000000", "+000863.400000000000000000000000000000",
        )
        # localcontext restores the previous Decimal settings after this block.
        # A precision of three makes accidental arithmetic rounding easy to detect.
        with localcontext() as context:
            # Traps turn rounding signals into exceptions that fail this test.
            context.prec = 3
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            for text in samples:
                with self.subTest(text=text):
                    row = source_row(); row["capacity"] = text
                    result = normalize_row("national", row)
                    # Numeric equality treats 1.0 and 1.00 as equal.
                    # as_tuple also checks sign, digits, and decimal exponent.
                    self.assertEqual(result.values["capacity"].as_tuple(), Decimal(text).as_tuple())
                    self.assertEqual(row["capacity"], text)
                    # Arrow may store fewer trailing zeros at scale six.
                    # Its converted value must still equal the original number.
                    array = pa.array([result.values["capacity"]], type=pa.decimal128(24, 6))
                    self.assertEqual(array[0].as_py(), Decimal(text))

    def test_signed_outage_and_unusual_percentages_are_not_clamped(self) -> None:
        # An unusual range is evidence for diagnostic checks, not permission
        # to replace negative values with zero or cap percentages at 100.
        for text in ("-999999999999999999.9999990000", "-0.000001", "101.0000000"):
            row = source_row(); row.update(outage=text, percentOutage=text)
            result = normalize_row("national", row)
            for name in ("outage", "percentOutage"):
                self.assertEqual(result.values[name].as_tuple(), Decimal(text).as_tuple())
                array = pa.array([result.values[name]], type=pa.decimal128(24, 6))
                self.assertEqual(array[0].as_py(), Decimal(text))

    def test_overflow_and_nonzero_seventh_digit_fail_for_every_measurement(self) -> None:
        # Overflow means too many integer digits. Excess scale means a nonzero
        # fractional digit would be lost. Both errors must preserve source text.
        cases = {"1000000000000000000": "decimal_overflow",
                 "0.0000001": "decimal_scale", "863.4000001": "decimal_scale",
                 "999999999999999999.9999991": "decimal_scale"}
        for name in ("capacity", "outage", "percentOutage"):
            for text, code in cases.items():
                for sign in ("", "-"):
                    with self.subTest(field=name, value=sign + text):
                        row = source_row(); row[name] = sign + text
                        with self.assertRaises(NormalizationError) as caught:
                            normalize_row("national", row)
                        self.assertEqual(caught.exception.code, code)
                        self.assertEqual(row[name], sign + text)

    def test_invalid_decimal_lexical_forms_fail(self) -> None:
        # Decimal accepts some forms that this source contract rejects.
        # Check spelling rules as well as whether a value could be converted.
        for text in ("NaN", "sNaN", "Infinity", "-Infinity", "1e2", "1_000", "1,000",
                     ".", "+.", "-.", "1.", " 1", "1 ", "1\n", "１２", "++1", "abc"):
            for name in ("capacity", "outage", "percentOutage"):
                row = source_row(); row[name] = text
                with self.subTest(field=name, value=text), self.assertRaises(NormalizationError) as caught:
                    normalize_row("national", row)
                self.assertEqual(caught.exception.code, "invalid_decimal")

    def test_negative_capacity_fails_but_zero_is_valid(self) -> None:
        for text in ("-1", "-0.000001"):
            row = source_row(); row["capacity"] = text
            with self.assertRaises(NormalizationError) as caught:
                normalize_row("national", row)
            self.assertEqual(caught.exception.code, "negative_capacity")
        # A minus sign on zero does not make its numeric value negative.
        for text in ("0", "-0.0000000", "+0.000000000"):
            row = source_row(); row["capacity"] = text
            self.assertEqual(normalize_row("national", row).values["capacity"], Decimal(0))

    def test_required_units_fail_when_missing_or_changed(self) -> None:
        # Keep valid measurement text so each failure comes from its unit label.
        for name in ("capacity", "outage", "percentOutage"):
            for value in (None, "kilowatts", "", 1):
                row = source_row(); row[f"{name}-units"] = value
                with self.subTest(field=name, value=value), self.assertRaises(NormalizationError) as caught:
                    normalize_row("national", row)
                self.assertEqual(caught.exception.code, "invalid_units")
            del row[f"{name}-units"]
            with self.assertRaises(NormalizationError):
                normalize_row("national", row)

    def test_unknown_fields_and_lexical_evidence_are_unchanged_on_success_and_failure(self) -> None:
        for capacity in ("863.4000000", "863.4000001"):
            row = source_row("facility")
            row.update(capacity=capacity, extra={"original": ["unchanged"]})
            # A deep copy also catches changes inside the nested evidence.
            # A shallow copy would share that nested object with the input.
            before = deepcopy(row)
            if capacity.endswith("1"):
                with self.assertRaises(NormalizationError):
                    normalize_row("facility", row)
            else:
                result = normalize_row("facility", row)
                self.assertEqual(list(result.values), DATASETS["facility"].schema.names)
                self.assertNotIn("extra", result.values)
            self.assertEqual(row, before)

    def test_errors_and_result_repr_do_not_echo_source_values(self) -> None:
        # A synthetic marker detects source text in routine error/result output.
        # This checks display behavior, not access control over result.values.
        marker = "synthetic-private-marker"
        row = source_row(); row["outage"] = marker
        with self.assertRaises(NormalizationError) as caught:
            normalize_row("national", row)
        self.assertNotIn(marker, str(caught.exception))
        self.assertNotIn(marker, repr(caught.exception))
        row = source_row("facility"); row["facilityName"] = marker
        self.assertNotIn(marker, repr(normalize_row("facility", row)))

    def test_unknown_dataset_and_nonrow_inputs_fail_safely(self) -> None:
        # Lists cannot serve as dictionary keys. The dataset type check must
        # reject them before a registry lookup can raise an unrelated TypeError.
        for dataset in ("private-marker", "", None, []):
            with self.assertRaises(NormalizationError) as caught:
                normalize_row(dataset, source_row())
            self.assertEqual(caught.exception.code, "unknown_dataset")
            self.assertNotIn("private-marker", str(caught.exception))
        for row in (None, [], "private-marker"):
            with self.assertRaises(NormalizationError) as caught:
                normalize_row("national", row)
            self.assertEqual(caught.exception.code, "invalid_row")


class ConnectorParsingRegressionTests(unittest.IsolatedAsyncioTestCase):
    """Check that parser input remains compatible with the asynchronous client."""

    async def test_parses_existing_sanitized_page_without_changing_it(self) -> None:
        for dataset in DATASETS:
            payload = {"response": {"frequency": "daily", "total": "1", "data": [source_row(dataset)]}}
            # MockTransport supplies this response without a network request.
            # The real client still parses and sanitizes the supplied response.
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
            settings = EIASettings(EIA_API_KEY="synthetic-offline-key")
            async with EIAClient(settings, transport=transport) as client:
                # getattr selects fetch_national_page, fetch_facility_page, or
                # fetch_generator_page so all three routes use the same check.
                page = await getattr(client, f"fetch_{dataset}_page")(
                    start=date(2026, 10, 1), end=date(2026, 10, 1),
                )
            before = deepcopy(page.response)
            result = normalize_row(dataset, page.data[0])
            self.assertEqual(result.values["capacity"].as_tuple(), Decimal("100.0000000").as_tuple())
            self.assertEqual(page.response, before)


if __name__ == "__main__":
    unittest.main()
