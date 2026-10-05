"""Check the documented newest-national request using synthetic transport."""
import unittest
from datetime import date
import httpx
from test_validate import reconciled
from trinity.config import EIASettings
from trinity.connector.client import EIAClient, EIAClientError


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_descending_one_row_and_sanitized_evidence(self):
        def response(request):
            self.assertEqual(request.url.params['sort[0][column]'],'period')
            self.assertEqual(request.url.params['sort[0][direction]'],'desc')
            self.assertEqual(request.url.params['length'],'1')
            return httpx.Response(200,json={'response':{'frequency':'daily','data':[
                {**reconciled()['national'][-1],'echo':'synthetic-secret'}]}})
        async with EIAClient(EIASettings(EIA_API_KEY='synthetic-secret'),transport=httpx.MockTransport(response)) as client:
            end,evidence=await client.discover_latest(start=date(2024,10,2))
        self.assertEqual(end,date.fromisoformat(reconciled()['national'][-1]['period']))
        self.assertNotIn('synthetic-secret',str(evidence))

    async def test_empty_malformed_and_future_dates_never_supply_a_window(self):
        source=reconciled()['national'][-1]
        for rows in ([],[{**source,'period':'not-a-date'}],[{**source,'period':'9999-01-01'}],[source,source]):
            async with EIAClient(EIASettings(EIA_API_KEY='synthetic'),transport=httpx.MockTransport(
                    lambda request:httpx.Response(200,json={'response':{'frequency':'daily','data':rows}}))) as client:
                with self.assertRaises(EIAClientError):await client.discover_latest(start=date(2024,10,2))

    async def test_failed_custody_prevents_http(self):
        calls=[]
        def reject(_event):raise RuntimeError('synthetic persistence failure')
        async with EIAClient(EIASettings(EIA_API_KEY='synthetic'),before_attempt=reject,
                transport=httpx.MockTransport(lambda request:calls.append(request))) as client:
            with self.assertRaises(RuntimeError):await client.discover_latest(start=date(2024,10,2))
        self.assertEqual(calls,[])
