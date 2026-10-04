"""Check all three live EIA routes for one fixed date using EIA_API_KEY.

Run this file explicitly; default test discovery excludes it.
Require a nonempty page and bounded pagination for each route.
These checks do not establish full-window coverage or publication readiness.
Missing credentials, request failures, and failed assertions fail the run.
"""

from datetime import date
import unittest

from trinity.connector.client import EIAClient


class LiveEIATests(unittest.IsolatedAsyncioTestCase):
    async def test_one_nonempty_page_from_each_route(self) -> None:
        # A fixed date keeps repeated checks on the same source window.
        day = date(2026, 10, 1)
        async with EIAClient() as client:
            for fetch in (
                client.fetch_national_page,
                client.fetch_facility_page,
                client.fetch_generator_page,
            ):
                with self.subTest(route=fetch.__name__):
                    page = await fetch(start=day, end=day, length=1)
                    self.assertEqual(len(page.data), 1)
                    self.assertEqual(page.data[0]["period"], day.isoformat())

    async def test_paginated_counts_for_each_route(self) -> None:
        day = date(2026, 10, 1)
        async with EIAClient() as client:
            for fetch in (client.fetch_national, client.fetch_facility, client.fetch_generator):
                with self.subTest(route=fetch.__name__):
                    result = await fetch(
                        start=day, end=day, page_size=50, max_pages=25, timeout_seconds=120
                    )
                    self.assertGreater(result.record_count, 0)
                    self.assertEqual(result.pages[-1].data, [])
                    self.assertEqual(result.page_count, result.data_page_count + 1)
                    self.assertEqual(
                        sum(len(page.data) for page in result.pages), result.record_count
                    )
                    if result.dataset != "facility" and result.advertised_total is not None:
                        self.assertTrue(result.total_matches)
                        self.assertGreaterEqual(result.data_page_count, result.minimum_data_pages)


if __name__ == "__main__":
    unittest.main()
