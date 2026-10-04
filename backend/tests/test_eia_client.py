"""Contract tests using synthetic EIA responses; no credentials or network needed."""

from copy import deepcopy
from dataclasses import asdict
from datetime import date
import io
import json
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import quote_plus

import httpx

from trinity.config import ConfigurationError
from trinity.connector.client import EIAClient, EIAClientError


_DAY = date(2026, 10, 1)
_KEY = "synthetic+key/for-tests"


def page_payload(dataset: str = "national") -> dict:
    """Synthetic values, not evidence of an EIA observation."""
    # Keep decimal text and leading-zero IDs so accidental numeric conversion is visible.
    row = {
        "period": _DAY.isoformat(),
        "capacity": "100.000000",
        "capacity-units": "megawatts",
        "outage": "12.500000",
        "outage-units": "megawatts",
        "percentOutage": "12.5",
        "percentOutage-units": "percent",
    }
    if dataset != "national":
        row.update(facility="0046", facilityName="Synthetic plant")
    if dataset == "generator":
        row["generator"] = "01"
    return {
        "response": {
            "frequency": "daily",
            "dateFormat": "YYYY-MM-DD",
            "total": "1",
            "data": [row],
        },
        "apiVersion": "2.1.14",
        "request": {"params": {"api_key": _KEY}},
    }


class EIAClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Each async test gets its own event loop and a synthetic environment key.
        # Register cleanup now so a failed test cannot leave that environment installed.
        self.environment = patch.dict(os.environ, {"EIA_API_KEY": _KEY}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    async def test_all_routes_use_one_transport_and_correct_parameters(self) -> None:
        seen = []
        routes = {
            "us-nuclear-outages": ("national", ["period"]),
            "facility-nuclear-outages": ("facility", ["period", "facility"]),
            "generator-nuclear-outages": ("generator", ["period", "facility", "generator"]),
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "api.eia.gov")
            route = request.url.path.split("/")[-3]
            dataset, fields = routes[route]
            params = request.url.params
            self.assertEqual(params["api_key"], _KEY)
            self.assertEqual(params["frequency"], "daily")
            self.assertEqual(params["start"], "2026-10-01")
            self.assertEqual(params["end"], "2026-10-01")
            self.assertEqual(params["offset"], "7")
            self.assertEqual(params["length"], "2")
            self.assertEqual(
                [params[f"data[{i}]"] for i in range(3)],
                ["capacity", "outage", "percentOutage"],
            )
            self.assertEqual(
                [params[f"sort[{i}][column]"] for i in range(len(fields))], fields
            )
            for i in range(len(fields)):
                self.assertEqual(params[f"sort[{i}][direction]"], "asc")
            seen.append(dataset)
            return httpx.Response(200, json=page_payload(dataset))

        # MockTransport runs the handler instead of making network requests. The
        # client still builds real HTTPX requests, so parameter and redaction checks apply.
        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            for dataset in ("national", "facility", "generator"):
                with self.subTest(dataset=dataset):
                    page = await getattr(client, f"fetch_{dataset}_page")(
                        start=_DAY, end=_DAY, offset=7, length=2
                    )
                    self.assertEqual(len(page.data), 1)
                    self.assertEqual(page.total, 1)
                    self.assertEqual(page.api_version, "2.1.14")
                    self.assertEqual(page.data[0]["capacity"], "100.000000")
                    if dataset != "national":
                        self.assertEqual(page.data[0]["facility"], "0046")
                    self.assertNotIn(_KEY, json.dumps(asdict(page)))
        self.assertEqual(seen, ["national", "facility", "generator"])

    async def test_empty_page_and_misleading_facility_total_are_valid(self) -> None:
        for rows in (page_payload("facility")["response"]["data"], []):
            payload = page_payload("facility")
            payload["response"].update(data=rows, total="95")
            async with EIAClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
            ) as client:
                result = await client.fetch_facility_page(start=_DAY, end=_DAY)
            self.assertEqual(result.total, 95)
            self.assertEqual(result.data, rows)

    async def test_invalid_arguments_make_no_request(self) -> None:
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=page_payload())

        cases = [
            {"start": "2026-10-01"}, {"end": date(2026, 9, 30)},
            {"offset": -1}, {"offset": True}, {"length": 0},
            {"length": 5001}, {"length": 1.5},
        ]
        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            for change in cases:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    await client.fetch_national_page(**{"start": _DAY, "end": _DAY, **change})
        self.assertEqual(calls, [])

    async def test_permanent_http_failures_do_not_retry_or_follow_redirects(self) -> None:
        # A redirect includes another host to expose accidental credential forwarding.
        for status in (301, 400, 401, 403, 404, 501):
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(
                    status, headers={"Location": "https://example.invalid/"},
                    text=f"unsafe upstream body {_KEY}",
                )

            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national_page(start=_DAY, end=_DAY)
            self.assertEqual(caught.exception.status_code, status)
            self.assertEqual(caught.exception.code, "http_error")
            self.assertNotIn(_KEY, str(caught.exception))
            self.assertEqual(len(calls), 1)

    async def test_timeout_and_transport_errors_are_safe(self) -> None:
        for error_type, code in ((httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "transport_error")):
            def handler(request):
                raise error_type(f"unsafe URL {request.url}", request=request)

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock):
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await client.fetch_national_page(start=_DAY, end=_DAY)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(_KEY, str(caught.exception))
            self.assertNotIn(quote_plus(_KEY), str(caught.exception))

    async def test_api_body_errors_and_malformed_pages_are_rejected(self) -> None:
        # HTTP success can contain API errors or invalid data. Change one shape
        # or value at a time to exercise each validation group with synthetic payloads.
        bad = [
            ({"error": _KEY, "code": 400}, "api_error"),
            ({"response": {"error": _KEY}}, "api_error"),
            ([], "invalid_response"),
            ({}, "invalid_response"),
        ]
        for field, value in (
            ("data", {}), ("data", [None]), ("frequency", "monthly"),
            ("total", -1), ("total", True), ("total", "1.5"),
        ):
            payload = page_payload()
            payload["response"][field] = value
            bad.append((payload, "invalid_response"))
        for field, value in (
            ("period", "2026-02-30"), ("period", "20261001"),
            ("period", "2026-09-30"), ("capacity", 100), ("outage", None),
            ("capacity-units", "kilowatts"), ("percentOutage", 12.5),
        ):
            payload = page_payload()
            payload["response"]["data"][0][field] = value
            bad.append((payload, "invalid_response"))
        payload = page_payload()
        payload["response"]["data"] *= 2
        bad.append((payload, "invalid_response"))
        for payload, expected in bad:
            with self.subTest(payload=payload):
                async with EIAClient(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
                ) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await client.fetch_national_page(start=_DAY, end=_DAY, length=1)
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn(_KEY, str(caught.exception))

    async def test_route_specific_identifiers_are_required(self) -> None:
        for dataset, field in (("facility", "facility"), ("generator", "generator")):
            payload = page_payload(dataset)
            del payload["response"]["data"][0][field]
            async with EIAClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
            ) as client:
                with self.assertRaises(EIAClientError):
                    await getattr(client, f"fetch_{dataset}_page")(start=_DAY, end=_DAY)

    async def test_invalid_json_is_rejected(self) -> None:
        async with EIAClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not JSON"))
        ) as client:
            with self.assertRaises(EIAClientError) as caught:
                await client.fetch_national_page(start=_DAY, end=_DAY)
        self.assertEqual(caught.exception.code, "invalid_json")

    async def test_optional_percent_is_preserved_and_secret_echoes_are_removed(self) -> None:
        # Echo both plain and URL-encoded forms. Removing only the request field
        # would still leak credentials from warnings and nested values.
        payload = deepcopy(page_payload())
        del payload["response"]["data"][0]["percentOutage"]
        payload["warning"] = "synthetic warning"
        payload["description"] = f"unsafe {_KEY} and {quote_plus(_KEY)}"
        payload["response"]["extra"] = {"api_key": _KEY, "note": f"api_key={quote_plus(_KEY)}"}
        async with EIAClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ) as client:
            result = await client.fetch_national_page(start=_DAY, end=_DAY)
        serialized = json.dumps(asdict(result))
        self.assertNotIn(_KEY, serialized)
        self.assertNotIn(quote_plus(_KEY), serialized)
        self.assertNotIn("request", serialized)
        self.assertNotIn("percentOutage", result.data[0])
        self.assertEqual(result.warnings["warning"], "synthetic warning")

    async def test_httpx_logging_masks_the_encoded_key(self) -> None:
        # Capture HTTPX's normal INFO output, where request URLs can expose keys.
        # Restore the logger in finally because it is shared across test cases.
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("httpx")
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            async with EIAClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=page_payload()))
            ) as client:
                await client.fetch_national_page(start=_DAY, end=_DAY)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertNotIn(_KEY, output.getvalue())
        self.assertNotIn(quote_plus(_KEY), output.getvalue())

    async def test_context_manager_closes_transport(self) -> None:
        class Transport(httpx.AsyncBaseTransport):
            closed = False

            async def handle_async_request(self, request):
                return httpx.Response(200, json=page_payload())

            async def aclose(self):
                self.closed = True

        transport = Transport()
        async with EIAClient(transport=transport) as client:
            await client.fetch_national_page(start=_DAY, end=_DAY)
        self.assertTrue(transport.closed)

    def test_missing_environment_key_prevents_client_creation(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                EIAClient()


if __name__ == "__main__":
    unittest.main()
