"""Validate one frozen candidate and retain each attempt as local evidence.

validate_candidate is the entry point. It reads saved files, never live EIA.
Required checks and diagnostics share one attempt and one manifest identity.
No function in this module uploads files or grants publication authority.
"""

import asyncio
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from trinity.connector import parquet
from trinity.connector.normalize import normalize_row
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import (
    Manifest, canonical_json, read_json, read_manifest, sha256,
)


CHECKSET = "trinity-data-v1"
DIAGNOSTIC_REGISTRY = "warnings-v1"
# Each pair is (check code, dataset scope). A tuple fixes the complete registry.
# The four cross-dataset checks use the literal scope "all", never None.
REQUIRED_CHECKS = tuple(
    (code, scope)
    for code in ("V01", "V02", "V03", "V04", "V05", "V06", "V07", "V08")
    for scope in (tuple(DATASETS) if code in ("V01", "V02", "V03", "V08") else ("all",))
)
DIAGNOSTIC_SCOPES = MappingProxyType({
    "D01": ("facility", "generator"),
    **{code: tuple(DATASETS) for code in ("D02", "D03", "D04", "D05", "D06")},
    "D07": ("facility", "generator"), "D08": tuple(DATASETS), "D09": ("facility",),
})
DIAGNOSTIC_CHECKS = tuple((code, scope) for code, scopes in DIAGNOSTIC_SCOPES.items()
                          for scope in scopes)
MESSAGES = MappingProxyType({
    "D01": "Facility label is missing.", "D02": "Source percentage is missing.",
    "D03": "Outage is negative.", "D04": "Outage exceeds capacity.",
    "D05": "Source percentage is outside 0 to 100.",
    "D06": "Source and computed percentages differ beyond the threshold.",
    "D07": "Entity membership changed.", "D08": "Reported capacity changed.",
    "D09": "Facility advertised total differs from the returned row count.",
})
_ROUTES = {dataset: f"https://api.eia.gov/v2/nuclear-outages/{route}/data/"
           for dataset, route in (("national", "us-nuclear-outages"),
                                  ("facility", "facility-nuclear-outages"),
                                  ("generator", "generator-nuclear-outages"))}


class ValidationError(RuntimeError):
    """Report a safe code and attempt identity without external error text."""

    def __init__(self, code: str, attempt_id: str | None = None) -> None:
        self.code = code
        self.attempt_id = attempt_id
        super().__init__(f"Candidate validation failed: {code}.")


@dataclass(frozen=True)
class CheckResult:
    """Bind one completed check to its immutable detail bytes and attempt.

    details_json uses bytes instead of a mutable dictionary. A caller cannot
    change a detail value after its digest has been assigned.
    """

    version_id: str
    attempt_id: str
    manifest_sha256: str
    checkset_version: str
    check_code: str
    check_revision: int
    dataset_key: str
    required: bool
    severity: str
    status: str
    checked_count: int
    failed_count: int
    details_json: bytes
    details_path: str
    checked_at: str

    def to_dict(self) -> dict:
        """Return a separate JSON-ready result, including its detail identity."""
        return {name: getattr(self, name) for name in (
            "version_id", "attempt_id", "manifest_sha256", "checkset_version",
            "check_code", "check_revision", "dataset_key", "required", "severity",
            "status", "checked_count", "failed_count", "details_path", "checked_at",
        )} | {"details": read_json(self.details_json), "details_sha256": sha256(self.details_json)}


@dataclass(frozen=True)
class ValidationReport:
    """Describe a completed local attempt, including completed failing checks.

    A failed report has no frozen warning digest or approval decision.
    Call verify_validation before using a passing report in a later stage.
    """

    root: Path
    manifest: Manifest
    attempt_id: str
    results: tuple[CheckResult, ...]
    diagnostics: tuple[CheckResult, ...]
    status: str
    warning_digest: str | None
    warning_count: int | None
    approval_required: bool | None
    validation_sha256: str
    diagnostics_sha256: str

    @property
    def evidence_path(self) -> str:
        """Return this attempt's relative directory; retries use another UUID."""
        return f"evidence/{self.attempt_id}"


@dataclass
class _Outcome:
    """Hold check observations before the journal assigns attempt metadata."""

    checked: int
    failed: int
    details: dict
    status: str | None = None


def _severity(code: str) -> str:
    """Reject unknown diagnostic codes before deriving a severity."""
    if code not in DIAGNOSTIC_SCOPES:
        raise ValidationError("unknown_diagnostic")
    return "info" if code in ("D07", "D08", "D09") else "warning"


def _bound_results(
    results: Sequence[CheckResult], expected: tuple, *, version_id: str,
    attempt_id: str, manifest_sha256: str, required: bool,
) -> bool:
    """Check the exact registry and common identity before considering status."""
    if len(results) != len(expected) or any(not isinstance(result, CheckResult) for result in results):
        return False
    if any(type(result.check_code) is not str or type(result.dataset_key) is not str for result in results):
        return False
    pairs = [(result.check_code, result.dataset_key) for result in results]
    if len(set(pairs)) != len(expected) or set(pairs) != set(expected):
        return False
    for result in results:
        if (result.version_id != version_id or result.attempt_id != attempt_id
                or result.manifest_sha256 != manifest_sha256
                or result.checkset_version != CHECKSET
                or type(result.check_revision) is not int or result.check_revision != 1
                or result.required is not required
                or result.severity != ("required" if required else _severity(result.check_code))
                or type(result.checked_count) is not int or result.checked_count < 0
                or type(result.failed_count) is not int
                or not 0 <= result.failed_count <= result.checked_count
                or result.status not in ("pass", "fail", "error")
                or (required and result.status == "pass" and result.checked_count == 0)
                or (result.status == "pass" and result.failed_count != 0)
                or (result.status == "fail" and result.failed_count == 0)):
            return False
        try:
            _utc_time(result.checked_at)
            if canonical_json(read_json(result.details_json)) != result.details_json:
                return False
        except Exception:
            return False
    return True


def required_checks_pass(
    results: Sequence[CheckResult], *, version_id: str, attempt_id: str,
    manifest_sha256: str,
) -> bool:
    """Require all 16 unique passing results from one manifest and attempt.

    Empty, partial, duplicate, mixed or unsupported results return False.
    This checks result structure only. It does not recheck file bytes.
    """
    return _bound_results(results, REQUIRED_CHECKS, version_id=version_id,
                          attempt_id=attempt_id, manifest_sha256=manifest_sha256,
                          required=True) and all(result.status == "pass" for result in results)


def diagnostic_identity(results: Sequence[CheckResult]) -> tuple[str, int, list[dict]]:
    """Hash completed diagnostic summaries in code/scope order.

    Require the whole registry, including completed checks with no affected
    rows. Error results or unknown severities cannot mean zero warnings.
    The caller must separately require all required checks to pass.
    """
    if not results or not isinstance(results[0], CheckResult) or not _bound_results(
        results, DIAGNOSTIC_CHECKS, version_id=results[0].version_id,
        attempt_id=results[0].attempt_id, manifest_sha256=results[0].manifest_sha256,
        required=False,
    ) or any(result.status == "error" for result in results):
        raise ValidationError("incomplete_diagnostics")
    summaries = [{"code": result.check_code, "dataset_key": result.dataset_key,
                  "severity": result.severity, "affected_count": result.failed_count,
                  "message": MESSAGES[result.check_code],
                  "details_sha256": sha256(result.details_json)}
                 for result in sorted(results, key=lambda item: (item.check_code, item.dataset_key))]
    body = {"registry": DIAGNOSTIC_REGISTRY, "summaries": summaries}
    count = sum(item["severity"] == "warning" and item["affected_count"] > 0 for item in summaries)
    return sha256(canonical_json(body)), count, summaries


def _millionths(value: Decimal) -> int:
    """Convert an exact decimal to an integer without ambient Decimal arithmetic."""
    # as_tuple gives sign, digits and base-ten exponent without rounding.
    # Python integers grow as needed; a sum can exceed DECIMAL(24,6).
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(map(str, digits)))
    power = exponent + 6
    if power < 0:
        coefficient, remainder = divmod(coefficient, 10 ** -power)
        if remainder:
            raise ValueError("inexact_millionths")
    else:
        coefficient *= 10 ** power
    return -coefficient if sign else coefficient


def _fixed(value: int) -> str:
    """Render arbitrary-size millionths as exact six-place measurement text."""
    whole, fraction = divmod(abs(value), 1_000_000)
    return f"{'-' if value < 0 else ''}{whole}.{fraction:06d}"


def _days(manifest: Manifest) -> list[date]:
    """Expand the inclusive requested window; never infer it from available rows."""
    return [manifest.requested_start + timedelta(days=offset)
            for offset in range((manifest.requested_end - manifest.requested_start).days + 1)]


def _key(dataset: str, row: dict) -> tuple:
    """Build the contract's daily key, including facility for generator rows."""
    return tuple(row[field] for field in DATASETS[dataset].key_fields)


def _source_pages(record: dict) -> list[dict]:
    """Read successful response envelopes, verifying their original checksums."""
    pages = []
    for attempt in record["attempts"]:
        body = attempt["sanitized_response"]
        if body is not None and sha256(body.encode()) != attempt["response_sha256"]:
            raise ValueError("source_checksum")
        if (attempt["http_status"] == 200 and attempt["error_code"] is None
                and attempt["api_status"] == "no_error_reported"):
            payload = read_json(body)
            if "error" in payload or "error" in payload["response"]:
                raise ValueError("source_api_error")
            pages.append(payload["response"])
    return pages


def _total(value) -> int | None:
    """Accept only the EIA client's nonnegative integer total forms."""
    if value is None:
        return None
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value and all("0" <= char <= "9" for char in value):
        return int(value)
    raise ValueError("invalid_total")


def _utc_time(value: str) -> datetime:
    """Require timezone-aware UTC evidence timestamps."""
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("non_utc_time")
    return stamp


def _source_complete(dataset: str, record: dict, manifest: Manifest) -> _Outcome:
    """Check progress, stable totals and empty-page exhaustion from saved attempts."""
    reasons = []
    if (record["final_status"] != "success" or record["error_code"] is not None
            or record["route"] != _ROUTES[dataset]
            or record["requested_start"] != manifest.requested_start.isoformat()
            or record["requested_end"] != manifest.requested_end.isoformat()
            or record["sort_fields"] != list(DATASETS[dataset].key_fields)):
        reasons.append("route_not_complete")
    offset = pages = retries = 0
    expected_attempt = 1
    length = None
    total = None
    exhausted = False
    seen = set()
    route_start = _utc_time(record["started_at"])
    route_end = _utc_time(record["completed_at"])
    previous_end = route_start
    # Reconstruct each request position. A successful short page must still
    # have a later empty probe. Retried failures do not advance the offset.
    for attempt in record["attempts"]:
        started, ended = _utc_time(attempt["started_at"]), _utc_time(attempt["completed_at"])
        if not route_start <= previous_end <= started <= ended <= route_end:
            reasons.append("attempt_times")
        previous_end = ended
        requested = attempt["requested_length"]
        if (type(requested) is not int or not 1 <= requested <= 5000
                or (length is not None and requested != length)
                or type(attempt["offset"]) is not int or attempt["offset"] != offset
                or type(attempt["attempt_number"]) is not int
                or attempt["attempt_number"] != expected_attempt or expected_attempt > 3
                or exhausted):
            reasons.append("request_progress")
        length = requested
        retries += expected_attempt > 1
        body = attempt["sanitized_response"]
        if body is not None and sha256(body.encode()) != attempt["response_sha256"]:
            reasons.append("response_checksum")
        if attempt["http_status"] != 200 or attempt["error_code"] is not None:
            retryable = (attempt["http_status"] in (429, 500, 502, 503, 504)
                         and attempt["error_code"] == "http_error") or (
                             attempt["http_status"] is None
                             and attempt["error_code"] in ("timeout", "transport_error"))
            if not retryable:
                reasons.append("failed_request")
            expected_attempt += 1
            continue
        payload = read_json(body)
        response = payload["response"]
        data = response["data"]
        if (attempt["api_status"] != "no_error_reported" or "error" in payload
                or "error" in response or len(data) > requested
                or type(attempt["actual_row_count"]) is not int
                or attempt["actual_row_count"] != len(data)
                or attempt["api_version"] != payload.get("apiVersion")):
            reasons.append("response_outcome")
        advertised = _total(response.get("total"))
        if advertised != _total(attempt["advertised_total"]):
            reasons.append("total_evidence")
        if advertised is not None:
            if total is not None and total != advertised:
                reasons.append("unstable_total")
            total = advertised
        for row in data:
            key = _key(dataset, row)
            # The recorded request supplies the key sort. Do not assume the
            # source sorts text IDs with Python's string comparison rules.
            # Repeated keys still prove overlap, irrespective of source order.
            if key in seen:
                reasons.append("repeated_key")
            seen.add(key)
        pages += 1
        offset += len(data)
        exhausted = not data
        expected_attempt = 1
    if not exhausted or expected_attempt != 1:
        reasons.append("missing_exhaustion")
    if (any(type(record[field]) is not int for field in ("pages_fetched", "records_fetched", "retries"))
            or record["pages_fetched"] != pages or record["records_fetched"] != offset
            or record["retries"] != retries):
        reasons.append("route_counts")
    if dataset != "facility" and total is not None and total != offset:
        reasons.append("total_mismatch")
    return _Outcome(1, int(bool(reasons)), {"reasons": sorted(set(reasons)),
                    "row_count": offset, "advertised_total": total})


def _schema_units(dataset: str, record: dict, rows: list[dict]) -> _Outcome:
    """Compare exact saved rows with parsed source rows and their unit proof."""
    pages = _source_pages(record)
    if record["frequency"] != "daily" or any(page.get("frequency") != "daily" for page in pages):
        return _Outcome(1, 1, {"reason": "source_frequency"})
    original = [normalize_row(dataset, row).values for page in pages for row in page["data"]]
    original.sort(key=lambda row: _key(dataset, row))
    saved = sorted(rows, key=lambda row: _key(dataset, row))
    # Comparing both lists preserves multiplicity. A set comparison would
    # hide a missing duplicate and could validate a silently deduplicated file.
    matches = original == saved
    return _Outcome(1, int(not matches), {"source_rows": len(original), "saved_rows": len(saved),
                                        "exact_values_match": matches})


def _unique_keys(dataset: str, rows: list[dict]) -> _Outcome:
    """Count duplicate observations, including duplicates with identical values."""
    counts = Counter(_key(dataset, row) for row in rows)
    duplicates = [{"key": key, "count": count} for key, count in sorted(counts.items()) if count > 1]
    return _Outcome(len(rows), sum(item["count"] - 1 for item in duplicates), {"duplicates": duplicates})


def _coverage(tables: dict, manifest: Manifest) -> _Outcome:
    """Compare every dataset with the requested dates, including common gaps."""
    expected = set(_days(manifest))
    details = {}
    failed = 0
    for dataset, rows in tables.items():
        dates = {row["period"] for row in rows}
        missing, extra = sorted(expected - dates), sorted(dates - expected)
        repeated = []
        if dataset == "national":
            repeated = sorted(day for day, count in Counter(row["period"] for row in rows).items() if count != 1)
        details[dataset] = {"missing_dates": missing, "extra_dates": extra,
                            "nonunique_national_dates": repeated}
        failed += bool(missing or extra or repeated)
    return _Outcome(3, failed, details)


def _facility_coverage(tables: dict) -> _Outcome:
    """Require facility/date groups in both directions without zero filling."""
    facilities = {(row["period"], row["facility"]) for row in tables["facility"]}
    generators = {(row["period"], row["facility"]) for row in tables["generator"]}
    missing_generators, missing_facilities = sorted(facilities - generators), sorted(generators - facilities)
    return _Outcome(len(facilities | generators), len(missing_generators) + len(missing_facilities),
                    {"missing_generator_groups": missing_generators, "missing_facility_rows": missing_facilities})


def _sums(rows: list[dict], fields: tuple[str, ...]) -> dict:
    """Group exact integer MW sums. An absent group stays absent."""
    # defaultdict calls this function only for a group that actually occurs.
    # Each group receives its own counters; missing entities get no row.
    groups = defaultdict(lambda: {"capacity": 0, "outage": 0})
    for row in rows:
        group = groups[tuple(row[field] for field in fields)]
        for measurement in ("capacity", "outage"):
            group[measurement] += _millionths(row[measurement])
    return dict(groups)


def _compare(expected: dict, observed: dict, comparison: str) -> list[dict]:
    """Record both MW fields for every union group and exact signed differences."""
    details = []
    for key in sorted(expected.keys() | observed.keys()):
        for measurement in ("capacity", "outage"):
            left = expected.get(key, {}).get(measurement)
            right = observed.get(key, {}).get(measurement)
            details.append({"comparison": comparison, "group": key, "measurement": measurement,
                            "expected": None if left is None else _fixed(left),
                            "observed": None if right is None else _fixed(right),
                            "difference": None if left is None or right is None else _fixed(right - left),
                            "matches": left is not None and right is not None and left == right})
    return details


def _reconcile(code: str, tables: dict) -> _Outcome:
    """Use Python integer millionths for zero-tolerance cross-grain comparisons."""
    if code == "V06":
        details = _compare(_sums(tables["facility"], ("period", "facility")),
                           _sums(tables["generator"], ("period", "facility")), "generator_to_facility")
    else:
        national = _sums(tables["national"], ("period",))
        details = [item for dataset in ("facility", "generator")
                   for item in _compare(national, _sums(tables[dataset], ("period",)), f"{dataset}_to_national")]
    return _Outcome(len(details), sum(not item["matches"] for item in details),
                    {"difference_direction": "observed - expected", "comparisons": details})


def _diagnostic(code: str, dataset: str, rows: list[dict], manifest: Manifest,
                source_result: CheckResult | None = None) -> _Outcome:
    """Evaluate one code/scope, retaining exact observations and applicability."""
    _severity(code)
    affected = []
    not_applicable = []
    checked = len(rows)
    if code == "D09":
        if source_result is None or source_result.status != "pass":
            raise ValueError("source_completeness_unavailable")
        source = read_json(source_result.details_json)
        total, actual = source["advertised_total"], source["row_count"]
        if total is not None and total != actual:
            affected.append({"advertised_total": total, "row_count": actual})
        checked = 1
    elif code in ("D07", "D08"):
        # Daily maps describe only observed entities. Never add a predecessor
        # before the window, and never carry capacity across an absent day.
        daily = defaultdict(dict)
        for row in rows:
            entity = _key(dataset, row)[1:]
            if code == "D08" and entity in daily[row["period"]]:
                raise ValueError("duplicate_capacity_observation")
            daily[row["period"]][entity] = row["capacity"]
        checked = 0
        days = _days(manifest)
        for previous, current in zip(days, days[1:]):
            before, after = daily[previous], daily[current]
            if code == "D07":
                for entity in sorted(before.keys() | after.keys()):
                    checked += 1
                    if entity not in before or entity not in after:
                        affected.append({"period": current, "previous_period": previous,
                                         "entity": entity, "change": "added" if entity in after else "removed"})
            else:
                for entity in sorted(before.keys() & after.keys()):
                    checked += 1
                    if before[entity] != after[entity]:
                        affected.append({"period": current, "previous_period": previous,
                                         "entity": entity, "previous_capacity": before[entity],
                                         "capacity": after[entity]})
    else:
        for row in rows:
            capacity, outage = row["capacity"], row["outage"]
            percentage = row["percentOutage"]
            observation = {"key": _key(dataset, row), "capacity": capacity,
                           "outage": outage, "percentOutage": percentage}
            applies = False
            if code == "D01":
                applies = row["facilityName"] is None
            elif code == "D02":
                applies = percentage is None
            elif code == "D03":
                applies = outage < 0
            elif code == "D04":
                applies = outage > capacity
            elif code == "D05":
                applies = percentage is not None and (percentage < 0 or percentage > 100)
            elif code == "D06":
                reasons = []
                if percentage is None:
                    reasons.append("missing_source_percentage")
                if capacity == 0:
                    reasons.append("zero_capacity")
                if reasons:
                    not_applicable.append({"key": _key(dataset, row), "reasons": reasons})
                    continue
                # Cross multiplication avoids division and rounding. P, C and
                # O are integer millionths. Equality at 0.0051 does not warn:
                # capacity=100, outage=10, P=10.005100 passes; 10.005101 warns.
                p, c, o = map(_millionths, (percentage, capacity, outage))
                difference = abs(p * c - 100 * o * 1_000_000)
                threshold = 5100 * c
                applies = difference > threshold
                observation.update(absolute_cross_difference=difference, cross_threshold=threshold)
            if applies:
                affected.append(observation)
    return _Outcome(checked, len(affected), {"affected": affected,
                    "not_applicable": not_applicable,
                    "eligible_count": checked - len(not_applicable)})


def _snapshot(root: int, manifest: Manifest) -> tuple[dict, dict, dict]:
    """Read only declared files, keeping per-dataset integrity failures visible."""
    tables = {dataset: None for dataset in DATASETS}
    integrity = {dataset: [] for dataset in DATASETS}
    sources = {}
    try:
        # The manifest may have changed since the attempt was reserved.
        read_manifest(parquet._read(root, "manifest.json"), manifest.digest)
        files = parquet._inventory(root)
        expected = {entry.storage_path for entry in manifest.entries}
        for path in files - expected:
            if path in parquet.SIDECARS and path != "failure.json":
                continue
            if path.startswith("evidence/") and path.endswith((".json", ".jsonl")):
                continue
            raise ValueError("unexpected_file")
    except Exception:
        for dataset in integrity:
            integrity[dataset].append("version_inventory")
    try:
        evidence = parquet._read(root, "source-evidence.json")
        if sha256(evidence) != manifest.source_evidence_sha256:
            raise ValueError("source_evidence_checksum")
        body = read_json(evidence)
        records = body["routes"]
        if (type(body["evidence_format"]) is not int or body["evidence_format"] != 1
                or len(records) != 3 or {item["dataset"] for item in records} != set(DATASETS)):
            raise ValueError("source_registry")
        sources = {record["dataset"]: record for record in records}
    except Exception:
        for dataset in integrity:
            integrity[dataset].append("source_evidence")
    for dataset in DATASETS:
        rows = []
        for entry in manifest.entries:
            if entry.dataset_key != dataset:
                continue
            try:
                actual, table = parquet._measure(dataset, entry.storage_path,
                                                  parquet._read(root, entry.storage_path))
                if actual != entry:
                    raise ValueError("file_identity")
                rows.extend(table.to_pylist())
            except Exception:
                integrity[dataset].append("file_identity")
        # A damaged data file cannot supply rows for dependent checks.
        # A global inventory defect still permits checks on readable bound data,
        # but its required V08 failures prevent successful validation.
        if "file_identity" not in integrity[dataset]:
            tables[dataset] = rows
    return tables, sources, integrity


def _required(code: str, scope: str, tables: dict, sources: dict,
              integrity: dict, manifest: Manifest) -> _Outcome:
    """Run one required check; missing inputs raise for an explicit error result."""
    if code == "V08":
        return _Outcome(1, int(bool(integrity[scope])), {"reasons": integrity[scope]})
    if code == "V01":
        return _source_complete(scope, sources[scope], manifest)
    if code in ("V02", "V03"):
        if tables[scope] is None:
            raise ValueError("saved_rows_unavailable")
        if code == "V02":
            return _schema_units(scope, sources[scope], tables[scope])
        return _unique_keys(scope, tables[scope])
    needed = ("facility", "generator") if code in ("V05", "V06") else tuple(DATASETS)
    if any(tables[dataset] is None for dataset in needed):
        raise ValueError("saved_rows_unavailable")
    if code == "V04":
        return _coverage(tables, manifest)
    if code == "V05":
        return _facility_coverage(tables)
    return _reconcile(code, tables)


def _evaluate(operation: Callable[[], _Outcome]) -> _Outcome:
    """Convert an unexecutable check to an error without exposing exception text."""
    try:
        return operation()
    except Exception:
        # Do not catch KeyboardInterrupt or asyncio.CancelledError here.
        # Cancellation stops the attempt; it is not a completed check failure.
        return _Outcome(0, 0, {"reason": "check_could_not_complete"}, "error")


class _Journal:
    """Append durable evidence within one exclusively reserved attempt directory."""

    def __init__(self, root: int, manifest: Manifest, attempt_id: str) -> None:
        self.root = root
        self.manifest = manifest
        self.attempt_id = attempt_id
        self.prefix = f"evidence/{attempt_id}"
        self.stream = None

    def __enter__(self):
        # dir_fd and O_NOFOLLOW retain Step 2's safe filesystem boundary.
        with parquet._parent(self.root, f"{self.prefix}/journal.jsonl") as (parent, name):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            self.stream = os.fdopen(descriptor, "wb")
            try:
                os.fsync(parent)
            except BaseException:
                self.stream.close()
                raise
        return self

    def __exit__(self, *_exception) -> None:
        self.stream.close()

    def append(self, record: dict) -> None:
        """Finish the file sync before allowing the next check to start."""
        self.stream.write(canonical_json(record) + b"\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def save_result(self, code: str, scope: str, outcome: _Outcome, required: bool) -> CheckResult:
        """Save detail bytes first, then append their bound result to the journal."""
        detail = canonical_json(outcome.details)
        path = f"{self.prefix}/{code}-{scope}.json"
        parquet._write_bytes(self.root, path, detail)
        if parquet._read(self.root, path) != detail:
            raise ValidationError("detail_readback")
        result = CheckResult(
            self.manifest.version_id, self.attempt_id, self.manifest.digest, CHECKSET,
            code, 1, scope, required, "required" if required else _severity(code),
            outcome.status or ("fail" if outcome.failed else "pass"),
            outcome.checked, outcome.failed, detail, path, datetime.now(UTC).isoformat(),
        )
        self.append({"event": "result", "result": result.to_dict()})
        return result


def _cancel_if_requested(cancelled: Callable[[], bool] | None) -> None:
    """Stop between operations; hard process deadlines belong to the supervisor."""
    if cancelled is not None and cancelled():
        raise ValidationError("cancelled")


def validate_candidate(
    root: Path, expected_sha256: str, *, cancelled: Callable[[], bool] | None = None,
    on_start=None,
) -> ValidationReport:
    """Validate saved Parquet and source evidence in one independent attempt.

    The caller supplies a frozen version directory and its retained manifest
    digest. Verify that manifest before reserving an attempt UUID. Reopen the
    declared files. Run V01-V08 as exactly 16 results and evaluate D01-D09.
    Save detail files and flush/fsync each result before the next check starts.

    Return a passed or failed report only after saving complete summaries.
    Freeze the warning identity only when all required checks pass and all
    diagnostics complete. Warnings require later approval, not a repair here.
    Results live in evidence/<attempt UUID>/ so a new attempt cannot overwrite
    earlier evidence or combine earlier passes. The input files never change.

    On cancellation or persistence failure, retain completed journal entries
    and an incomplete summary where writable, then raise. A partial directory
    never proves readiness. This function does not upload, approve or publish.
    """
    attempt_id = None
    try:
        with parquet._directory(Path(root)) as descriptor:
            manifest = read_manifest(parquet._read(descriptor, "manifest.json"), expected_sha256)
            if Path(root).name != manifest.version_id:
                raise ValueError("version_directory")
            # Reserve attempts only after a valid frozen manifest exists.
            # Revalidation always creates another UUID, even for unchanged files.
            attempt_id = str(uuid4())
            with parquet._parent(descriptor, f"evidence/{attempt_id}") as (parent, name):
                os.mkdir(name, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            # Bind the attempt before the first validation check. Failed custody
            # stops validation while preserving its reserved local directory.
            if on_start is not None:
                on_start(attempt_id, manifest.digest)
            return _validate_reserved(descriptor, Path(root), manifest, attempt_id, cancelled)
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("validation_io_or_input", attempt_id) from None


def _validate_reserved(root: int, root_path: Path, manifest: Manifest, attempt_id: str,
                       cancelled: Callable[[], bool] | None) -> ValidationReport:
    """Run and persist one reserved attempt, retaining failures without repair."""
    results, diagnostics = [], []
    prefix = f"evidence/{attempt_id}"
    binding = {"version_id": manifest.version_id, "attempt_id": attempt_id,
               "manifest_sha256": manifest.digest, "checkset_version": CHECKSET,
               "contract_version": manifest.contract_version,
               "requested_start": manifest.requested_start, "requested_end": manifest.requested_end}
    try:
        with _Journal(root, manifest, attempt_id) as journal:
            journal.append({"event": "started", **binding, "expected_checks": REQUIRED_CHECKS,
                            "diagnostic_registry": DIAGNOSTIC_REGISTRY,
                            "expected_diagnostics": DIAGNOSTIC_CHECKS})
            _cancel_if_requested(cancelled)
            tables, sources, integrity = _snapshot(root, manifest)
            for code, scope in REQUIRED_CHECKS:
                _cancel_if_requested(cancelled)
                outcome = _evaluate(lambda: _required(code, scope, tables, sources, integrity, manifest))
                results.append(journal.save_result(code, scope, outcome, True))
            for code, scope in DIAGNOSTIC_CHECKS:
                _cancel_if_requested(cancelled)
                source = next((item for item in results if item.check_code == "V01"
                               and item.dataset_key == scope), None)
                outcome = _evaluate(lambda: _diagnostic(code, scope, tables[scope], manifest, source))
                diagnostics.append(journal.save_result(code, scope, outcome, False))

            passed = required_checks_pass(results, version_id=manifest.version_id,
                                           attempt_id=attempt_id, manifest_sha256=manifest.digest)
            warning_digest = warning_count = approval_required = None
            summaries = []
            final_error = None
            try:
                # A file changed during evaluation must not inherit passing
                # results from the earlier snapshot. Preserve those results,
                # but fail the attempt instead of replacing the manifest.
                parquet._check_files(root, manifest)
                read_manifest(parquet._read(root, "manifest.json"), manifest.digest)
                digest, count, complete_summaries = diagnostic_identity(diagnostics)
            except Exception:
                passed = False
                final_error = "files_changed_or_diagnostics_incomplete"
            else:
                if passed:
                    warning_digest, warning_count, summaries = digest, count, complete_summaries
                    approval_required = count > 0
            _cancel_if_requested(cancelled)
            status = "passed" if passed else "failed"
            diagnostic_body = {**binding, "registry": DIAGNOSTIC_REGISTRY, "frozen": passed,
                               "warning_digest": warning_digest, "warning_count": warning_count,
                               "approval_required": approval_required, "summaries": summaries,
                               "evaluations": [result.to_dict() for result in diagnostics]}
            validation_body = {**binding, "status": status, "expected_checks": REQUIRED_CHECKS,
                               "results": [result.to_dict() for result in results], "error_code": final_error}
            # Both immutable summaries must exist before completion is recorded.
            # A disk failure after one write leaves an incomplete attempt.
            diagnostic_bytes = canonical_json(diagnostic_body)
            validation_bytes = canonical_json(validation_body)
            parquet._write_bytes(root, f"{prefix}/diagnostics.json", diagnostic_bytes)
            parquet._write_bytes(root, f"{prefix}/validation.json", validation_bytes)
            if (parquet._read(root, f"{prefix}/diagnostics.json") != diagnostic_bytes
                    or parquet._read(root, f"{prefix}/validation.json") != validation_bytes):
                raise ValidationError("summary_readback")
            journal.append({"event": "completed", **binding, "status": status,
                            "diagnostics_sha256": sha256(diagnostic_bytes),
                            "validation_sha256": sha256(validation_bytes)})
            report = ValidationReport(root_path, manifest, attempt_id, tuple(results), tuple(diagnostics),
                                      status, warning_digest, warning_count, approval_required,
                                      sha256(validation_bytes), sha256(diagnostic_bytes))
            if passed:
                verify_validation(report)
            return report
    except BaseException as error:
        # BaseException includes controlled cancellation. Retain prior synced
        # records before propagating it. Never copy raw external error text.
        try:
            parquet._write_bytes(root, f"{prefix}/incomplete.json", canonical_json({
                **binding, "status": "incomplete", "completed_results": len(results),
                "completed_diagnostics": len(diagnostics),
                "error_code": "cancelled" if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError))
                or isinstance(error, ValidationError) and error.code == "cancelled" else "validation_incomplete",
            }))
        except Exception:
            pass
        if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
            raise
        code = "cancelled" if isinstance(error, ValidationError) and error.code == "cancelled" else "validation_incomplete"
        raise ValidationError(code, attempt_id) from None


def verify_validation(report: ValidationReport) -> None:
    """Recheck a passing receipt and its current files before a later stage.

    Reject changed data, source evidence, result files, missing completion or
    incomplete attempts. This is an offline handoff guard, not an S3 upload.
    """
    bound_directory = False
    try:
        if report.status != "passed" or not required_checks_pass(
            report.results, version_id=report.manifest.version_id, attempt_id=report.attempt_id,
            manifest_sha256=report.manifest.digest,
        ):
            raise ValueError("required_checks")
        if not _bound_results(report.diagnostics, DIAGNOSTIC_CHECKS,
                              version_id=report.manifest.version_id, attempt_id=report.attempt_id,
                              manifest_sha256=report.manifest.digest, required=False):
            raise ValueError("diagnostic_attempt_binding")
        digest, count, _summaries = diagnostic_identity(report.diagnostics)
        if (report.warning_digest != digest or type(report.warning_count) is not int
                or report.warning_count != count
                or report.approval_required is not (count > 0)):
            raise ValueError("diagnostic_identity")
        with parquet._directory(report.root) as root:
            # This check retains the original manifest identity on failure.
            read_manifest(parquet._read(root, "manifest.json"), report.manifest.digest)
            if report.root.name != report.manifest.version_id:
                raise ValueError("version_directory")
            bound_directory = True
            parquet._check_files(root, report.manifest)
            files = parquet._inventory(root)
            if f"{report.evidence_path}/incomplete.json" in files:
                raise ValueError("incomplete_attempt")
            for name, expected in (("validation", report.validation_sha256),
                                   ("diagnostics", report.diagnostics_sha256)):
                data = parquet._read(root, f"{report.evidence_path}/{name}.json")
                if sha256(data) != expected:
                    raise ValueError("summary_checksum")
                saved = read_json(data)
                if (saved["attempt_id"] != report.attempt_id
                        or saved["manifest_sha256"] != report.manifest.digest
                        or saved["version_id"] != report.manifest.version_id
                        or saved["checkset_version"] != CHECKSET
                        or saved["contract_version"] != report.manifest.contract_version
                        or saved["requested_start"] != report.manifest.requested_start.isoformat()
                        or saved["requested_end"] != report.manifest.requested_end.isoformat()):
                    raise ValueError("summary_binding")
                if name == "validation":
                    if (saved["status"] != "passed" or saved["error_code"] is not None
                            or saved["expected_checks"] != [list(pair) for pair in REQUIRED_CHECKS]):
                        raise ValueError("validation_summary")
                elif (saved["registry"] != DIAGNOSTIC_REGISTRY or saved["frozen"] is not True
                      or saved["warning_digest"] != digest or type(saved["warning_count"]) is not int
                      or saved["warning_count"] != count
                      or saved["approval_required"] is not report.approval_required
                      or saved["summaries"] != _summaries):
                    raise ValueError("diagnostic_summary")
                expected_results = report.results if name == "validation" else report.diagnostics
                if saved["results" if name == "validation" else "evaluations"] != [item.to_dict() for item in expected_results]:
                    raise ValueError("result_identity")
            for result in (*report.results, *report.diagnostics):
                if parquet._read(root, result.details_path) != result.details_json:
                    raise ValueError("detail_checksum")
            events = [read_json(line) for line in parquet._read(
                root, f"{report.evidence_path}/journal.jsonl").splitlines()]
            if (len(events) != 2 + len(REQUIRED_CHECKS) + len(DIAGNOSTIC_CHECKS)
                    or events[0]["event"] != "started"
                    or events[0]["attempt_id"] != report.attempt_id
                    or events[0]["manifest_sha256"] != report.manifest.digest
                    or events[0]["expected_checks"] != [list(pair) for pair in REQUIRED_CHECKS]
                    or events[0]["expected_diagnostics"] != [list(pair) for pair in DIAGNOSTIC_CHECKS]
                    or [event.get("result") for event in events[1:-1]] != [
                        result.to_dict() for result in (*report.results, *report.diagnostics)]
                    or any(event.get("event") != "result" for event in events[1:-1])):
                raise ValueError("journal_evidence")
            completion = events[-1]
            if (completion["event"] != "completed" or completion["status"] != "passed"
                    or completion["attempt_id"] != report.attempt_id
                    or completion["manifest_sha256"] != report.manifest.digest
                    or completion["validation_sha256"] != report.validation_sha256
                    or completion["diagnostics_sha256"] != report.diagnostics_sha256):
                raise ValueError("completion_evidence")
    except Exception:
        if bound_directory:
            # Preserve a failed later-stage recheck beside the original attempt.
            # Do not replace its successful snapshot or rewrite any identity.
            try:
                with parquet._directory(report.root) as root:
                    parquet._write_bytes(root, f"{report.evidence_path}/recheck-{uuid4()}.json",
                                         canonical_json({"status": "failed", "stage": "artifact_recheck",
                                                         "attempt_id": report.attempt_id,
                                                         "manifest_sha256": report.manifest.digest,
                                                         "error_code": "validation_no_longer_valid"}))
            except Exception:
                pass
        raise ValidationError("validation_no_longer_valid", report.attempt_id) from None
