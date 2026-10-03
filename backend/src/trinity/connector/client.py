"""One-page EIA requests. Pagination and retry orchestration belong above this layer."""

from dataclasses import dataclass
from datetime import date
import logging
import re
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

from trinity.config import EIASettings, load_eia_settings


_BASE_URL = "https://api.eia.gov/v2/nuclear-outages/"
_ROUTES = {
    "national": ("us-nuclear-outages/data/", ("period",)),
    "facility": ("facility-nuclear-outages/data/", ("period", "facility")),
    "generator": ("generator-nuclear-outages/data/", ("period", "facility", "generator")),
}
_KEY_IN_URL = re.compile(r"(api_key=)[^&\s\"']+", re.IGNORECASE)
_PRIVATE_FIELDS = {"request", "api_key", "apikey", "authorization", "cookie", "set-cookie"}


class _RedactAPIKey(logging.Filter):
    """HTTPX logs request URLs at INFO; EIA requires its key in the URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _KEY_IN_URL.sub(r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


_LOG_FILTER = _RedactAPIKey()


class EIAClientError(RuntimeError):
    """Safe failure details, without response bodies or credential-bearing URLs."""

    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        suffix = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"EIA request failed: {code}{suffix}.")


@dataclass(frozen=True)
class EIAResponsePage:
    """Sanitized source response; a page is not proof of complete extraction."""

    response: dict[str, Any]
    total: int | None
    api_version: str | None
    warnings: dict[str, Any]

    @property
    def data(self) -> list[dict[str, Any]]:
        return self.response["data"]


def _sanitize(value: Any, secret: str) -> Any:
    """Remove echoed credentials while preserving source values and unit metadata."""
    if isinstance(value, dict):
        return {
            key: _sanitize(item, secret)
            for key, item in value.items()
            if key.casefold() not in _PRIVATE_FIELDS
        }
    if isinstance(value, list):
        return [_sanitize(item, secret) for item in value]
    if isinstance(value, str):
        for token in {secret, quote(secret, safe=""), quote_plus(secret)}:
            value = value.replace(token, "[REDACTED]")
        return _KEY_IN_URL.sub(r"\1[REDACTED]", value)
    return value


def _validate_page(
    payload: Any, key_fields: tuple[str, ...], start: date, end: date, length: int
) -> EIAResponsePage:
    """Check the envelope and row shape; decimal normalization is a later stage."""
    invalid = EIAClientError("invalid_response")
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
    if response.get("frequency") != "daily" or not isinstance(rows, list):
        raise invalid
    if len(rows) > length:
        raise invalid

    for row in rows:
        if not isinstance(row, dict):
            raise invalid
        for field in (*key_fields, "capacity", "outage"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise invalid
        if row.get("percentOutage") is not None and not isinstance(row["percentOutage"], str):
            raise invalid
        if row.get("facilityName") is not None and not isinstance(row["facilityName"], str):
            raise invalid
        try:
            period = date.fromisoformat(row["period"])
        except ValueError:
            raise invalid from None
        if period.isoformat() != row["period"] or not start <= period <= end:
            raise invalid
        for field in ("capacity", "outage"):
            if row.get(f"{field}-units") != "megawatts":
                raise invalid
        if row.get("percentOutage") not in (None, ""):
            if row.get("percentOutage-units") != "percent":
                raise invalid

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
    # The known facility total mismatch must not reject an otherwise valid page.
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
    """

    def __init__(
        self,
        settings: EIASettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings if settings is not None else load_eia_settings()
        # Keep the filter installed: removing it when one client closes could
        # expose URLs from another active client. It stores no credential.
        logging.getLogger("httpx").addFilter(_LOG_FILTER)
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> "EIAClient":
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch_national_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        return await self._fetch_page("national", start, end, offset, length)

    async def fetch_facility_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        return await self._fetch_page("facility", start, end, offset, length)

    async def fetch_generator_page(
        self, *, start: date, end: date, offset: int = 0, length: int = 5000
    ) -> EIAResponsePage:
        return await self._fetch_page("generator", start, end, offset, length)

    async def _fetch_page(
        self, dataset: str, start: date, end: date, offset: int, length: int
    ) -> EIAResponsePage:
        if type(start) is not date or type(end) is not date or start > end:
            raise ValueError("start and end must be dates with start <= end.")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer.")
        if type(length) is not int or not 1 <= length <= 5000:
            raise ValueError("length must be an integer from 1 to 5000.")

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

        try:
            reply = await self._http.get(route, params=params)
        except httpx.TimeoutException:
            raise EIAClientError("timeout") from None
        except httpx.HTTPError:
            raise EIAClientError("transport_error") from None
        if reply.status_code != 200:
            raise EIAClientError("http_error", status_code=reply.status_code)
        try:
            payload = reply.json()
        except (ValueError, UnicodeError):
            raise EIAClientError("invalid_json") from None
        sanitized = _sanitize(payload, secret)
        return _validate_page(sanitized, key_fields, start, end, length)
