"""Shared EIA requests with bounded pagination and temporary-failure retries."""

import asyncio
from asyncio import sleep
from dataclasses import dataclass, replace
from datetime import date
import hashlib
import json
import logging
import math
import re
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

from trinity.config import EIASettings, load_eia_settings
from trinity.connector.retrieval import (
    RetrievalAttempt, RetrievalMetadata, RetrievalTracker, utc_now,
)


_BASE_URL = "https://api.eia.gov/v2/nuclear-outages/"
# Each tuple lists the fields that identify a daily row and set its request order.
# Generator labels are unique only within a facility, so both IDs belong in the key.
_ROUTES = {
    "national": ("us-nuclear-outages/data/", ("period",)),
    "facility": ("facility-nuclear-outages/data/", ("period", "facility")),
    "generator": ("generator-nuclear-outages/data/", ("period", "facility", "generator")),
}
# Capture the parameter name, then match its value up to a URL/text separator.
# The replacement keeps the name and hides the value, regardless of letter case.
_KEY_IN_URL = re.compile(r"(api_key=)[^&\s\"']+", re.IGNORECASE)
_PRIVATE_FIELDS = {"request", "api_key", "apikey", "authorization", "cookie", "set-cookie"}
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (1.0, 3.0)
_PAGE_TIMEOUT_SECONDS = 30.0
_RETRYABLE_TRANSPORT_ERRORS = (
    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
    httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError,
)


class _RedactAPIKey(logging.Filter):
    """HTTPX logs request URLs at INFO; EIA requires its key in the URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask URL keys in the rendered log message before handlers receive it."""
        # getMessage applies logging arguments first. Clear them after replacement
        # so a handler cannot format the original arguments into the safe message.
        record.msg = _KEY_IN_URL.sub(r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


_LOG_FILTER = _RedactAPIKey()


class EIAClientError(RuntimeError):
    """Safe failure details, without response bodies or credential-bearing URLs."""

    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        # Page calls leave metadata empty. Collection calls attach final evidence.
        self.metadata: RetrievalMetadata | None = None
        self.code = code
        self.status_code = status_code
        suffix = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"EIA request failed: {code}{suffix}.")


class EIAInputError(ValueError):
    """Invalid collection arguments, with a finalized retrieval record."""

    def __init__(self, metadata: RetrievalMetadata) -> None:
        self.metadata = metadata
        super().__init__(metadata.error_message)


class EIARetrievalCancelled(asyncio.CancelledError):
    """Cancellation still propagates, carrying the completed route evidence."""

    def __init__(self, metadata: RetrievalMetadata) -> None:
        self.metadata = metadata
        super().__init__("EIA retrieval cancelled.")


# frozen=True prevents field replacement, but the nested lists and dictionaries
# remain mutable. Treat returned source evidence as read-only when using it later.
@dataclass(frozen=True)
class EIAResponsePage:
    """Sanitized source response; a page is not proof of complete extraction."""

    response: dict[str, Any]
    total: int | None
    api_version: str | None
    warnings: dict[str, Any]

    @property
    def data(self) -> list[dict[str, Any]]:
        """Return sanitized source rows without numeric normalization."""
        return self.response["data"]


@dataclass(frozen=True)
class EIACollection:
    """Rows and page evidence from one route after confirmed empty-page exhaustion."""

    dataset: str
    data: list[dict[str, Any]]
    pages: list[EIAResponsePage]
    advertised_total: int | None
    page_size: int
    metadata: RetrievalMetadata | None = None

    @property
    def record_count(self) -> int:
        """Return the number of collected rows."""
        return len(self.data)

    @property
    def page_count(self) -> int:
        """Count accepted pages, including the final empty probe."""
        return len(self.pages)

    @property
    def data_page_count(self) -> int:
        """Count pages that contain rows, excluding the final empty probe."""
        return sum(bool(page.data) for page in self.pages)

    @property
    def total_matches(self) -> bool | None:
        """Compare the row count with the advertised total; return None if absent."""
        if self.advertised_total is None:
            return None
        return self.record_count == self.advertised_total

    @property
    def minimum_data_pages(self) -> int | None:
        """Return a page-count lower bound, or None for facility or absent totals."""
        # Round up: five rows at two rows per page need at least three data pages.
        # Short responses can require more. A misleading facility total gives no bound.
        if self.dataset == "facility" or self.advertised_total is None:
            return None
        return (self.advertised_total + self.page_size - 1) // self.page_size


def _sanitize(value: Any, secret: str) -> Any:
    """Copy JSON values and remove known private fields and echoed credentials.

    Preserve other source values and unit metadata. Leave the input unchanged.
    """
    if isinstance(value, dict):
        # Rebuild nested objects, including their field names. Drop known private
        # fields entirely because their contents are not needed as data evidence.
        return {
            _sanitize(key, secret): _sanitize(item, secret)
            for key, item in value.items()
            if key.casefold() not in _PRIVATE_FIELDS
        }
    if isinstance(value, list):
        return [_sanitize(item, secret) for item in value]
    if isinstance(value, str):
        # EIA may echo the key directly or URL-encoded. quote_plus also encodes spaces.
        for token in {secret, quote(secret, safe=""), quote_plus(secret)}:
            value = value.replace(token, "[REDACTED]")
        return _KEY_IN_URL.sub(r"\1[REDACTED]", value)
    return value


def _validate_page(
    payload: Any, key_fields: tuple[str, ...], start: date, end: date, length: int
) -> EIAResponsePage:
    """Check a sanitized JSON page and return its source rows and metadata.

    Require daily rows inside the requested window, route keys, and expected units.
    Raise EIAClientError for API errors or invalid shapes. Keep measurement text
    unchanged; this function does not parse numbers or establish full coverage.
    """
    invalid = EIAClientError("invalid_response")
    # HTTP 200 does not prove success. EIA can put an error at either JSON level.
    if not isinstance(payload, dict):
        raise invalid
    if "error" in payload:
        raise EIAClientError("api_error")
    response = payload.get("response")
    if not isinstance(response, dict):
        raise invalid
    if "error" in response:
        raise EIAClientError("api_error")
    rows = response.get("data")
    # Reject unexpected frequency or excess rows before accepting the page shape.
    if response.get("frequency") != "daily" or not isinstance(rows, list):
        raise invalid
    if len(rows) > length:
        raise invalid

    for row in rows:
        if not isinstance(row, dict):
            raise invalid
        # Unpack the route's key fields, then add required measurements.
        # IDs such as "0046" and decimal text must remain strings at this stage.
        for field in (*key_fields, "capacity", "outage"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise invalid
        if row.get("percentOutage") is not None and not isinstance(row["percentOutage"], str):
            raise invalid
        if row.get("facilityName") is not None and not isinstance(row["facilityName"], str):
            raise invalid
        # fromisoformat accepts some alternate forms. The round trip requires
        # YYYY-MM-DD exactly, and the window check rejects unrelated observations.
        try:
            period = date.fromisoformat(row["period"])
        except ValueError:
            raise invalid from None
        if period.isoformat() != row["period"] or not start <= period <= end:
            raise invalid
        # Require MW for both measurements. Missing or empty percentOutage does
        # not require a percent unit, but a nonempty value does.
        for field in ("capacity", "outage"):
            if row.get(f"{field}-units") != "megawatts":
                raise invalid
        if row.get("percentOutage") not in (None, ""):
            if row.get("percentOutage-units") != "percent":
                raise invalid

    # Accept a nonnegative integer or digit-only text such as "95". Reject "1.5",
    # negatives, and True. Python treats bool as an int subclass, so use exact types.
    advertised = response.get("total")
    if advertised is None:
        total = None
    elif type(advertised) is int and advertised >= 0:
        total = advertised
    elif isinstance(advertised, str) and re.fullmatch(r"[0-9]+", advertised):
        try:
            total = int(advertised)
        except ValueError:
            raise invalid from None
    else:
        raise invalid
    version = payload.get("apiVersion")
    if version is not None and not isinstance(version, str):
        raise invalid
    return EIAResponsePage(
        response=response,
        total=total,
        api_version=version,
        warnings={key: payload[key] for key in ("warning", "description", "warnings") if key in payload},
    )


class EIAClient:
    """Reuse one asynchronous HTTPX connection pool for all three EIA routes.

    The default constructor loads EIA_API_KEY from the current environment.
    Use an async context manager, or call aclose() when finished.
    Inject a trusted transport only for testing.

    Fetch methods use inclusive dates and preserve source measurement strings.
    Page methods raise ValueError for invalid inputs and EIAClientError for
    request or response failures. They do not attach retrieval metadata.
    Collection methods return only after an empty page confirms exhaustion.
    Their failures carry metadata in EIAInputError or EIAClientError;
    EIARetrievalCancelled carries cancellation evidence. No partial collection
    is returned. max_pages includes the empty probe; timeout_seconds covers
    the whole route, including retries.
    """

    def __init__(
        self,
        settings: EIASettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Explicit settings support tests; otherwise read the process environment.
        self._settings = settings if settings is not None else load_eia_settings()
        # Keep the filter installed: removing it when one client closes could
        # expose URLs from another active client. It stores no credential.
        logging.getLogger("httpx").addFilter(_LOG_FILTER)
        # Keep credentials on the configured endpoint. Disable redirects and
        # environment proxies; cap connection setup separately from other I/O.
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> "EIAClient":
        """Open the shared HTTP client and return this connector."""
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the shared HTTP client when its context ends."""
        await self._http.__aexit__(*args)

    async def aclose(self) -> None:
        """Close the shared HTTP client when used without a context manager."""
        await self._http.aclose()

    async def fetch_national_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        """Fetch one national page under the shared page rules."""
        return await self._fetch_page("national", start, end, offset, length)

    async def fetch_facility_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        """Fetch one facility page under the shared page rules."""
        return await self._fetch_page("facility", start, end, offset, length)

    async def fetch_generator_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        """Fetch one generator page under the shared page rules."""
        return await self._fetch_page("generator", start, end, offset, length)

    async def fetch_national(
        self, *, start: date, end: date, page_size: int = 5000,
        max_pages: int = 1000, timeout_seconds: float = 300.0,
    ) -> EIACollection:
        """Collect national rows under the shared collection limits and failure rules."""
        return await self._fetch_all("national", start, end, page_size, max_pages, timeout_seconds)

    async def fetch_facility(
        self, *, start: date, end: date, page_size: int = 5000,
        max_pages: int = 1000, timeout_seconds: float = 300.0,
    ) -> EIACollection:
        """Collect facility rows; retain advertised total mismatches as evidence."""
        return await self._fetch_all("facility", start, end, page_size, max_pages, timeout_seconds)

    async def fetch_generator(
        self, *, start: date, end: date, page_size: int = 5000,
        max_pages: int = 1000, timeout_seconds: float = 300.0,
    ) -> EIACollection:
        """Collect generator rows under the shared collection limits and failure rules."""
        return await self._fetch_all("generator", start, end, page_size, max_pages, timeout_seconds)

    async def _fetch_all(
        self, dataset: str, start: date, end: date, page_size: int,
        max_pages: int, timeout_seconds: float,
    ) -> EIACollection:
        """Collect one route and attach safe final evidence to results or failures."""
        # Each invocation owns a tracker, even when calls share the HTTP client.
        tracker = self.retrieval_tracker(dataset, start, end)
        try:
            collection = await self._collect(
                dataset, start, end, page_size, max_pages, timeout_seconds, tracker
            )
        except asyncio.CancelledError:
            # Preserve cancellation as cancellation, with the evidence gathered so far.
            raise EIARetrievalCancelled(tracker.finish(
                "cancelled", error_code="cancelled", error_message="EIA retrieval cancelled."
            )) from None
        except EIAClientError as error:
            error.metadata = tracker.finish(
                "failed", error_code=error.code, error_message=str(error)
            )
            raise
        except ValueError:
            # Do not copy arbitrary exception text into evidence.
            raise EIAInputError(tracker.finish(
                "failed", error_code="invalid_arguments",
                error_message="Invalid retrieval date range or limits."
            )) from None
        except Exception:
            # Unexpected exceptions may contain private values. Expose only a safe code.
            error = EIAClientError("unexpected_error")
            error.metadata = tracker.finish(
                "failed", error_code=error.code, error_message=str(error)
            )
            raise error from None
        return replace(collection, metadata=tracker.finish("success"))

    @staticmethod
    def retrieval_tracker(dataset: str, start: date, end: date) -> RetrievalTracker:
        """Start route evidence; retain invalid date inputs as None for safe output."""
        route, fields = _ROUTES[dataset]
        return RetrievalTracker(
            dataset, _BASE_URL + route,
            start if type(start) is date else None,
            end if type(end) is date else None, fields,
        )

    async def _collect(
        self, dataset: str, start: date, end: date, page_size: int,
        max_pages: int, timeout_seconds: float, tracker: RetrievalTracker,
    ) -> EIACollection:
        """Accumulate unique source rows until an empty page, or fail without partial output."""
        # The budget includes the terminal empty page. Two one-row data pages need
        # max_pages=3 to succeed; max_pages=2 fails because exhaustion is unconfirmed.
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer including the empty probe.")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number.")

        # Keep both source pages and combined rows. The key set detects overlap
        # across pages even when the source revises a row's measurements.
        data: list[dict[str, Any]] = []
        pages: list[EIAResponsePage] = []
        seen: set[tuple[str, ...]] = set()
        key_fields = _ROUTES[dataset][1]
        advertised_total: int | None = None
        offset = 0
        loop = asyncio.get_running_loop()
        # The event loop clock is monotonic. Clock/calendar changes cannot extend
        # this route budget, and timeout_at cancels pending requests or retry waits.
        deadline = loop.time() + timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                for _ in range(max_pages):
                    if loop.time() >= deadline:
                        raise EIAClientError("pagination_deadline")
                    page = await self._fetch_page(dataset, start, end, offset, page_size, tracker)
                    # Count fetched evidence even if a later collection check rejects it.
                    tracker.pages_fetched += 1
                    tracker.records_fetched += len(page.data)
                    if loop.time() >= deadline:
                        raise EIAClientError("pagination_deadline")
                    pages.append(page)
                    if page.total is not None:
                        # A changing total means pages may describe different source
                        # states. Reject that inconsistency on every route.
                        if advertised_total is not None and page.total != advertised_total:
                            raise EIAClientError("unstable_total")
                        advertised_total = page.total

                    for row in page.data:
                        key = tuple(row[field] for field in key_fields)
                        if key in seen:
                            # Reject overlap and repeated pages even if their values changed.
                            raise EIAClientError("duplicate_key")
                        seen.add(key)
                    data.extend(page.data)
                    # Facility totals can disagree with returned rows; keep that evidence.
                    if dataset != "facility" and advertised_total is not None:
                        if len(data) > advertised_total or (
                            not page.data and len(data) != advertised_total
                        ):
                            raise EIAClientError("total_mismatch")
                    if not page.data:
                        return EIACollection(dataset, data, pages, advertised_total, page_size)
                    # A short page is not exhaustion. Probe after its actual last row.
                    offset += len(page.data)
        except TimeoutError:
            raise EIAClientError("pagination_deadline") from None
        # Never return partial data when the empty probe could not be reached.
        raise EIAClientError("page_limit")

    async def _fetch_page(
        self, dataset: str, start: date, end: date, offset: int, length: int,
        tracker: RetrievalTracker | None = None,
    ) -> EIAResponsePage:
        """Fetch one bounded page, remove credentials, and check its source shape.

        Invalid arguments raise ValueError before HTTP access. Request or response
        failures raise EIAClientError. Record attempts only when a tracker is supplied.
        """
        # Use exact types to reject bool as an offset/length and datetime as a date.
        # A length of 5000 is valid; 5001 exceeds this client's page limit.
        if type(start) is not date or type(end) is not date or start > end:
            raise ValueError("start and end must be dates with start <= end.")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer.")
        if type(length) is not int or not 1 <= length <= 5000:
            raise ValueError("length must be an integer from 1 to 5000.")

        # EIA expects indexed parameter names for measurements and sort columns.
        # Sort by the full natural key so pagination has a consistent row order.
        route, key_fields = _ROUTES[dataset]
        secret = self._settings.eia_api_key.get_secret_value()
        params = {
            "api_key": secret,
            "frequency": "daily",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "offset": str(offset),
            "length": str(length),
        }
        for index, field in enumerate(("capacity", "outage", "percentOutage")):
            params[f"data[{index}]"] = field
        for index, field in enumerate(key_fields):
            params[f"sort[{index}][column]"] = field
            params[f"sort[{index}][direction]"] = "asc"

        # Retries share this page deadline; collection calls also retain the route deadline.
        deadline = asyncio.get_running_loop().time() + _PAGE_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                reply = await self._request_with_retries(route, params, tracker)
                # Sanitize before validation or return. Callers never receive the
                # raw JSON object, which may contain echoed request credentials.
                try:
                    payload = reply.json()
                except (ValueError, UnicodeError):
                    raise EIAClientError("invalid_json") from None
                sanitized = _sanitize(payload, secret)
                page = _validate_page(sanitized, key_fields, start, end, length)
                if asyncio.get_running_loop().time() >= deadline:
                    raise EIAClientError("request_deadline")
                return page
        except TimeoutError:
            raise EIAClientError("request_deadline") from None

    async def _request_with_retries(
        self, route: str, params: dict[str, str], tracker: RetrievalTracker | None = None,
    ) -> httpx.Response:
        """Try the same GET at most three times for selected temporary failures.

        Return HTTP 200 for later JSON validation. Raise a safe EIAClientError for
        permanent errors or exhausted retries. Let caller cancellation propagate.
        """
        attempt = 0
        while True:
            attempt += 1
            if tracker is not None and attempt > 1:
                # A cancelled backoff must not count a retry that never started.
                tracker.retries += 1
            try:
                reply = await self._recorded_request(route, params, attempt, tracker)
            except _RETRYABLE_TRANSPORT_ERRORS as error:
                # Only the explicit temporary-error list reaches another attempt.
                code = "timeout" if isinstance(error, httpx.TimeoutException) else "transport_error"
                failure = EIAClientError(code)
            except httpx.TimeoutException:
                # Pool acquisition failure is local, not a temporary EIA response.
                raise EIAClientError("timeout") from None
            except httpx.HTTPError:
                # Do not retry arbitrary configuration, TLS, or protocol failures.
                raise EIAClientError("transport_error") from None
            else:
                if reply.status_code == 200:
                    return reply
                failure = EIAClientError("http_error", status_code=reply.status_code)
                if reply.status_code not in _RETRYABLE_STATUSES:
                    raise failure
            if attempt == 3:
                raise failure from None
            # Wait one second, then three seconds. The enclosing deadlines can
            # cancel these waits; a retry does not receive a new time budget.
            await sleep(_RETRY_DELAYS[attempt - 1])

    async def _recorded_request(
        self, route: str, params: dict[str, str], attempt: int,
        tracker: RetrievalTracker | None,
    ) -> httpx.Response:
        """Send one GET and capture sanitized evidence when a tracker is supplied.

        Return the response for status and page checks. On failure, retain attempt
        evidence in the tracker and propagate the exception to retry handling.
        """
        if tracker is None:
            return await self._http.get(route, params=params)
        started = utc_now()
        reply = None
        api_status = "no_response"
        error_code = None
        version = total = count = body = digest = None
        try:
            # Save response evidence before page validation. Even a rejected page
            # can explain why the route failed, but it is not an accepted data page.
            reply = await self._http.get(route, params=params)
            api_status = "unknown"
            if reply.status_code != 200:
                error_code = "http_error"
            try:
                payload = _sanitize(reply.json(), self._settings.eia_api_key.get_secret_value())
                body = json.dumps(
                    payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False,
                )
                # Hash the saved sanitized text, not the original secret-bearing response.
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if isinstance(payload, dict):
                    response = payload.get("response")
                    response = response if isinstance(response, dict) else {}
                    # Absence of an API error field is evidence only, not validation success.
                    api_status = "error" if "error" in payload or "error" in response else "no_error_reported"
                    version = payload.get("apiVersion")
                    version = version if isinstance(version, str) else None
                    total = response.get("total")
                    total = total if type(total) in (int, str) else None
                    rows = response.get("data")
                    count = len(rows) if isinstance(rows, list) else None
            except (ValueError, UnicodeError):
                # Arbitrary non-JSON bodies are not saved. There are no saved
                # response bytes to hash; do not invent a checksum for them.
                api_status = "invalid_json"
                if error_code is None:
                    error_code = "invalid_json"
            return reply
        except asyncio.CancelledError:
            error_code = "interrupted"
            raise
        except httpx.TimeoutException:
            error_code = "timeout"
            raise
        except httpx.HTTPError:
            error_code = "transport_error"
            raise
        except Exception:
            error_code = "unexpected_error"
            raise
        finally:
            # finally runs on success, failure, and cancellation. Append exactly
            # one attempt even when no response arrived, using None for missing facts.
            tracker.attempts.append(RetrievalAttempt(
                offset=int(params["offset"]), requested_length=int(params["length"]),
                attempt_number=attempt, started_at=started, completed_at=utc_now(),
                http_status=reply.status_code if reply is not None else None,
                api_status=api_status, api_version=version, advertised_total=total,
                actual_row_count=count, error_code=error_code,
                sanitized_response=body, response_sha256=digest,
            ))
