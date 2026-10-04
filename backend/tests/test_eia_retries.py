"""Retry policy checks with synthetic responses and controlled backoff."""

import asyncio
from datetime import date
import os
import unittest
from unittest.mock import AsyncMock, call, patch

import httpx

from trinity.connector.client import EIAClient, EIAClientError


_DAY = date(2026, 10, 1)
_KEY = "synthetic-retry-key"


def success():
    return httpx.Response(
        200, json={"response": {"frequency": "daily", "total": "0", "data": []}}
    )


class RetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"EIA_API_KEY": _KEY}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    async def test_each_retryable_status_stops_after_three_attempts(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                requests = []

                def handler(request):
                    requests.append(request)
                    return httpx.Response(status, text=f"unsafe body {_KEY}")

                with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                    async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                        with self.assertRaises(EIAClientError) as caught:
                            await client.fetch_national_page(start=_DAY, end=_DAY)
                self.assertEqual(len(requests), 3)
                self.assertEqual(backoff.await_args_list, [call(1.0), call(3.0)])
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn(_KEY, str(caught.exception))

    async def test_all_routes_recover_without_changing_request_parameters(self):
        for dataset in ("national", "facility", "generator"):
            requests = []

            def handler(request):
                requests.append(request)
                return httpx.Response(503) if len(requests) < 3 else success()

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    result = await getattr(client, f"fetch_{dataset}_page")(
                        start=_DAY, end=_DAY, offset=7, length=2
                    )
            self.assertEqual(result.data, [])
            self.assertEqual(len(requests), 3)
            self.assertTrue(all(request.url == requests[0].url for request in requests))
            self.assertEqual(backoff.await_args_list, [call(1.0), call(3.0)])

    async def test_first_attempt_success_does_not_wait(self):
        requests = []

        def handler(request):
            requests.append(request)
            return success()

        with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                await client.fetch_national_page(start=_DAY, end=_DAY)
        self.assertEqual(len(requests), 1)
        backoff.assert_not_awaited()

    async def test_permanent_failure_stops_immediately_even_after_a_retry(self):
        for status in (400, 401, 403, 404, 422, 501):
            for first_status in (None, 503):
                requests = []

                def handler(request):
                    requests.append(request)
                    code = first_status if first_status and len(requests) == 1 else status
                    return httpx.Response(code)

                with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                    async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                        with self.assertRaises(EIAClientError) as caught:
                            await client.fetch_national_page(start=_DAY, end=_DAY)
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(len(requests), 2 if first_status else 1)
                self.assertEqual(backoff.await_args_list, [call(1.0)] if first_status else [])

    async def test_http_200_body_errors_and_bad_json_are_never_retried(self):
        for reply in (
            httpx.Response(200, json={"error": "upstream error", "code": 500}),
            httpx.Response(200, text="not JSON"),
            httpx.Response(200, json={"response": {"data": "wrong shape"}}),
        ):
            requests = []

            def handler(request):
                requests.append(request)
                return reply

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError):
                        await client.fetch_national_page(start=_DAY, end=_DAY)
            self.assertEqual(len(requests), 1)
            backoff.assert_not_awaited()

    async def test_selected_temporary_transport_errors_are_bounded(self):
        for error_type in (
            httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
            httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError,
        ):
            requests = []

            def handler(request):
                requests.append(request)
                raise error_type(f"unsafe {_KEY}", request=request)

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await client.fetch_national_page(start=_DAY, end=_DAY)
            self.assertEqual(len(requests), 3)
            self.assertEqual(backoff.await_args_list, [call(1.0), call(3.0)])
            self.assertNotIn(_KEY, str(caught.exception))

    async def test_other_transport_errors_do_not_retry(self):
        for error_type in (httpx.ConnectError, httpx.PoolTimeout, httpx.LocalProtocolError):
            requests = []

            def handler(request):
                requests.append(request)
                raise error_type(f"unsafe {_KEY}", request=request)

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError):
                        await client.fetch_national_page(start=_DAY, end=_DAY)
            self.assertEqual(len(requests), 1)
            backoff.assert_not_awaited()

    async def test_pagination_retries_current_offset_without_duplicating_records(self):
        offsets = []
        attempts = {}

        def handler(request):
            offset = int(request.url.params["offset"])
            offsets.append(offset)
            attempts[offset] = attempts.get(offset, 0) + 1
            if offset == 1 and attempts[offset] == 1:
                return httpx.Response(502)
            rows = [] if offset == 2 else [{
                "period": f"2026-10-0{offset + 1}",
                "capacity": "100.0", "capacity-units": "megawatts",
                "outage": "10.0", "outage-units": "megawatts",
            }]
            return httpx.Response(
                200, json={"response": {"frequency": "daily", "total": "2", "data": rows}}
            )

        with patch("trinity.connector.client.sleep", new_callable=AsyncMock) as backoff:
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                result = await client.fetch_national(
                    start=_DAY, end=date(2026, 10, 2), page_size=1
                )
        self.assertEqual(offsets, [0, 1, 1, 2])
        self.assertEqual(result.record_count, 2)
        self.assertEqual(result.page_count, 3)  # Successful pages, not failed attempts.
        self.assertEqual(result.metadata.pages_fetched, 3)
        self.assertEqual(result.metadata.records_fetched, 2)
        self.assertEqual(result.metadata.retries, 1)
        self.assertEqual(len(result.metadata.attempts), 4)
        backoff.assert_awaited_once_with(1.0)

    async def test_page_deadline_interrupts_backoff_without_another_attempt(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(429)

        async def waiting_backoff(delay):
            await asyncio.Event().wait()

        with patch("trinity.connector.client._PAGE_TIMEOUT_SECONDS", 0.01):
            with patch("trinity.connector.client.sleep", side_effect=waiting_backoff):
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await client.fetch_national_page(start=_DAY, end=_DAY)
        self.assertEqual(caught.exception.code, "request_deadline")
        self.assertEqual(len(requests), 1)

    async def test_collection_deadline_interrupts_backoff_without_resetting(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(503)

        async def waiting_backoff(delay):
            await asyncio.Event().wait()

        with patch("trinity.connector.client.sleep", side_effect=waiting_backoff):
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national(start=_DAY, end=_DAY, timeout_seconds=0.01)
        self.assertEqual(caught.exception.code, "pagination_deadline")
        self.assertEqual(len(requests), 1)

    async def test_caller_cancellation_is_not_retried(self):
        requests = []
        sleeping = asyncio.Event()

        def handler(request):
            requests.append(request)
            return httpx.Response(503)

        async def waiting_backoff(delay):
            sleeping.set()
            await asyncio.Event().wait()

        with patch("trinity.connector.client.sleep", side_effect=waiting_backoff):
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                task = asyncio.create_task(client.fetch_national_page(start=_DAY, end=_DAY))
                await asyncio.wait_for(sleeping.wait(), timeout=1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
