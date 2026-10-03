"""Opt-in live check: export EIA_API_KEY, then run this file explicitly."""

from datetime import date
import unittest

from trinity.connector.client import EIAClient


class LiveEIATests(unittest.IsolatedAsyncioTestCase):
    async def test_one_nonempty_page_from_each_route(self) -> None:
        # A fixed date within A9's supported history makes this check reproducible.
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


if __name__ == "__main__":
    unittest.main()
