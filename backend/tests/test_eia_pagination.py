"""Pagination checks against a synthetic HTTPX transport; no live API calls."""

import asyncio
from copy import deepcopy
from datetime import date, timedelta
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from trinity.connector.client import EIAClient, EIAClientError


_START = date(2026, 10, 1)
_END = date(2026, 10, 5)


def rows_for(dataset, count):
    """Build synthetic rows with distinct natural keys for the requested route."""
    rows = []
    for index in range(count):
        row = {
            "period": (_START + timedelta(days=index)).isoformat()
            if dataset == "national" else _START.isoformat(),
            "capacity": "100.0", "capacity-units": "megawatts",
            "outage": "10.0", "outage-units": "megawatts",
            "percentOutage": "10.0", "percentOutage-units": "percent",
        }
        if dataset != "national":
            row["facility"] = f"{index // 2:04d}" if dataset == "generator" else f"{index:04d}"
        if dataset == "generator":
            # The same generator label in another facility is a different key.
            row["generator"] = str(index % 2)
        rows.append(row)
    return rows


def response(rows, total=None):
    """Wrap synthetic rows in an EIA response with an optional advertised total."""
    body = {"response": {"frequency": "daily", "data": rows}, "apiVersion": "2.1.14"}
    if total is not None:
        body["response"]["total"] = str(total)
    return httpx.Response(200, json=body)


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Replace the environment with a synthetic key. MockTransport handlers
        # below serve pages locally; none of these tests request live EIA data.
        environment = patch.dict(os.environ, {"EIA_API_KEY": "synthetic-pagination-key"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    async def test_all_routes_collect_rows_and_count_the_empty_probe(self):
        for dataset in ("national", "facility", "generator"):
            with self.subTest(dataset=dataset):
                rows = rows_for(dataset, 5)
                offsets = []

                def handler(request):
                    offset = int(request.url.params["offset"])
                    offsets.append(offset)
                    self.assertEqual(request.url.params["length"], "2")
                    return response(rows[offset:offset + 2], len(rows))

                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    result = await getattr(client, f"fetch_{dataset}")(
                        start=_START, end=_END, page_size=2
                    )
                self.assertEqual(offsets, [0, 2, 4, 5])
                self.assertEqual(result.data, rows)
                self.assertEqual(result.record_count, 5)
                self.assertEqual(result.page_count, 4)
                self.assertEqual(result.data_page_count, 3)
                self.assertEqual(sum(len(page.data) for page in result.pages), result.record_count)
                self.assertEqual(result.pages[-1].data, [])
                self.assertTrue(result.total_matches)
                self.assertEqual(result.minimum_data_pages, None if dataset == "facility" else 3)

    async def test_exact_multiple_still_requires_an_empty_probe(self):
        rows = rows_for("national", 4)
        offsets = []

        def handler(request):
            offset = int(request.url.params["offset"])
            offsets.append(offset)
            return response(rows[offset:offset + 2], 4)

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            result = await client.fetch_national(start=_START, end=_END, page_size=2, max_pages=3)
        self.assertEqual(offsets, [0, 2, 4])
        self.assertEqual(result.page_count, 3)

    async def test_short_nonterminal_pages_advance_by_actual_count(self):
        # Short pages can precede more data. Skipping by requested length would
        # lose rows; stopping at the first short page would return a partial result.
        rows = rows_for("national", 5)
        sizes = {0: 1, 1: 2, 3: 1, 4: 1, 5: 0}
        offsets = []

        def handler(request):
            offset = int(request.url.params["offset"])
            offsets.append(offset)
            return response(rows[offset:offset + sizes[offset]], 5)

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            result = await client.fetch_national(start=_START, end=_END, page_size=2)
        self.assertEqual(offsets, [0, 1, 3, 4, 5])
        self.assertEqual(result.data, rows)
        self.assertEqual(result.data_page_count, 4)
        self.assertEqual(result.minimum_data_pages, 3)

    async def test_empty_route_has_one_probe_and_zero_records(self):
        async with EIAClient(
            transport=httpx.MockTransport(lambda request: response([], 0))
        ) as client:
            result = await client.fetch_national(start=_START, end=_END, max_pages=1)
        self.assertEqual((result.page_count, result.data_page_count, result.record_count), (1, 0, 0))
        self.assertEqual(result.minimum_data_pages, 0)
        self.assertTrue(result.total_matches)

    async def test_no_total_uses_exhaustion_without_inventing_metadata(self):
        rows = rows_for("national", 3)

        def handler(request):
            offset = int(request.url.params["offset"])
            return response(rows[offset:offset + 2])

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            result = await client.fetch_national(start=_START, end=_END, page_size=2)
        self.assertEqual(result.data, rows)
        self.assertIsNone(result.advertised_total)
        self.assertIsNone(result.total_matches)
        self.assertIsNone(result.minimum_data_pages)

    async def test_total_supplied_only_on_later_page_is_checked(self):
        rows = rows_for("national", 3)

        def handler(request):
            offset = int(request.url.params["offset"])
            return response(rows[offset:offset + 2], 3 if offset else None)

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            result = await client.fetch_national(start=_START, end=_END, page_size=2)
        self.assertEqual(result.advertised_total, 3)
        self.assertTrue(result.total_matches)

    async def test_facility_total_mismatch_is_retained_as_evidence(self):
        # Test totals both below and above the fetched count. Facility completion
        # depends on an empty page, not on either misleading total.
        rows = rows_for("facility", 3)
        for total in (1, 95):
            def handler(request):
                offset = int(request.url.params["offset"])
                return response(rows[offset:offset + 2], total)

            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                result = await client.fetch_facility(start=_START, end=_END, page_size=2)
            self.assertEqual(result.record_count, 3)
            self.assertEqual(result.advertised_total, total)
            self.assertFalse(result.total_matches)
            self.assertIsNone(result.minimum_data_pages)
            self.assertEqual(result.page_count, 3)

    async def test_national_and_generator_total_mismatches_fail(self):
        for dataset in ("national", "generator"):
            for total in (2, 4):
                rows = rows_for(dataset, 3)

                def handler(request):
                    offset = int(request.url.params["offset"])
                    return response(rows[offset:offset + 2], total)

                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await getattr(client, f"fetch_{dataset}")(
                            start=_START, end=_END, page_size=2
                        )
                self.assertEqual(caught.exception.code, "total_mismatch")

    async def test_changing_total_even_on_empty_probe_fails_every_route(self):
        # A stable mismatch is allowed for facilities; a changing total is not.
        for dataset in ("national", "facility", "generator"):
            rows = rows_for(dataset, 2)

            def handler(request):
                offset = int(request.url.params["offset"])
                return response(rows if offset == 0 else [], 2 if offset == 0 else 3)

            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await getattr(client, f"fetch_{dataset}")(
                        start=_START, end=_END, page_size=2
                    )
            self.assertEqual(caught.exception.code, "unstable_total")

    async def test_repeated_overlapping_and_duplicate_rows_fail(self):
        rows = rows_for("national", 3)
        changed = deepcopy(rows[0])
        changed["outage"] = "11.0"
        cases = [
            [rows[:2], rows[:2]],           # repeated page
            [rows[:2], rows[1:]],           # overlap
            [[rows[0], rows[0]]],           # duplicate within one page
            [[rows[0]], [changed]],         # same key, revised measurements
        ]
        for batches in cases:
            calls = []

            def handler(request):
                calls.append(int(request.url.params["offset"]))
                return response(batches[len(calls) - 1])

            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national(start=_START, end=_END, page_size=2)
            self.assertEqual(caught.exception.code, "duplicate_key")

    async def test_error_after_a_good_page_does_not_return_partial_success(self):
        for failure in (
            httpx.Response(503, text="temporary failure"),
            httpx.Response(200, json={"error": "synthetic error", "code": 400}),
        ):
            calls = []

            def handler(request):
                calls.append(request)
                return response(rows_for("national", 1)) if len(calls) == 1 else failure

            with patch("trinity.connector.client.sleep", new_callable=AsyncMock):
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError):
                        await client.fetch_national(start=_START, end=_END)
            self.assertEqual(len(calls), 4 if failure.status_code == 503 else 2)

    async def test_page_budget_fails_instead_of_truncating(self):
        # Both data rows fit, but the budget lacks the empty probe needed for success.
        rows = rows_for("national", 2)
        offsets = []

        def handler(request):
            offset = int(request.url.params["offset"])
            offsets.append(offset)
            return response(rows[offset:offset + 1], 2)

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(EIAClientError) as caught:
                await client.fetch_national(start=_START, end=_END, page_size=1, max_pages=2)
        self.assertEqual(caught.exception.code, "page_limit")
        self.assertEqual(offsets, [0, 1])

    async def test_total_deadline_cancels_an_inflight_request(self):
        # The mock outlasts the route deadline. Its finally block proves the
        # request was cancelled instead of continuing after the caller failed.
        cancelled = []

        async def handler(request):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)
            return response([])

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(EIAClientError) as caught:
                await client.fetch_national(start=_START, end=_END, timeout_seconds=0.01)
        self.assertEqual(caught.exception.code, "pagination_deadline")
        self.assertEqual(cancelled, [True])

    async def test_invalid_limits_make_no_request(self):
        # NaN and infinity can defeat ordinary comparisons. True behaves like 1
        # in Python, but none of these values is a valid finite numeric budget.
        calls = []

        def handler(request):
            calls.append(request)
            return response([])

        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            for limits in (
                {"max_pages": 0}, {"max_pages": True}, {"timeout_seconds": 0},
                {"timeout_seconds": float("nan")}, {"timeout_seconds": float("inf")},
                {"timeout_seconds": True}, {"page_size": 0}, {"page_size": 5001},
            ):
                with self.subTest(limits=limits), self.assertRaises(ValueError):
                    await client.fetch_national(start=_START, end=_END, **limits)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
