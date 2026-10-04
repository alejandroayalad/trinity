"""Retrieval evidence and orchestration checks; synthetic HTTP only."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from trinity.connector.__main__ import main
from trinity.connector.client import EIAClient, EIAClientError, EIAInputError
from trinity.connector.pipeline import DATASETS, retrieve_all
from test_eia_pagination import response, rows_for

DAY = date(2026, 10, 1)
KEY = "synthetic-retrieval-secret"


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"EIA_API_KEY": KEY}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    async def test_each_route_success_has_counts_times_and_terminal_probe(self):
        for dataset in DATASETS:
            def handler(request):
                rows = rows_for(dataset, 1) if request.url.params["offset"] == "0" else []
                return response(rows, 1)
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                result = await getattr(client, f"fetch_{dataset}")(start=DAY, end=DAY)
            meta = result.metadata
            self.assertEqual(meta.dataset, dataset)
            self.assertEqual(meta.final_status, "success")
            self.assertEqual((meta.pages_fetched, meta.records_fetched, meta.retries), (2, 1, 0))
            self.assertEqual(len(meta.attempts), 2)
            self.assertEqual(meta.attempts[-1].actual_row_count, 0)
            self.assertLessEqual(meta.started_at, meta.completed_at)
            self.assertEqual(meta.started_at.utcoffset().total_seconds(), 0)
            self.assertIsNone(meta.error_message)
            self.assertEqual(meta.requested_start, DAY)

    async def test_each_route_failure_keeps_counts_and_exhausted_retries(self):
        for dataset in DATASETS:
            def handler(request):
                if request.url.params["offset"] == "0":
                    return response(rows_for(dataset, 1), 1)
                return httpx.Response(503, json={"error": KEY, "request": {"api_key": KEY}})
            with patch("trinity.connector.client.sleep", new_callable=AsyncMock):
                async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaises(EIAClientError) as caught:
                        await getattr(client, f"fetch_{dataset}")(start=DAY, end=DAY)
            meta = caught.exception.metadata
            self.assertEqual(meta.final_status, "failed")
            self.assertEqual((meta.pages_fetched, meta.records_fetched, meta.retries), (1, 1, 2))
            self.assertEqual([a.offset for a in meta.attempts], [0, 1, 1, 1])
            self.assertEqual([a.http_status for a in meta.attempts], [200, 503, 503, 503])
            self.assertEqual(meta.error_code, "http_error")
            self.assertNotIn(KEY, json.dumps(meta.to_dict()))

    async def test_saved_response_checksum_and_redaction(self):
        payload = {"apiVersion": "2.1", "request": {"api_key": KEY}, KEY: "echoed field name",
                   "warning": f"echo {KEY}", "authorization": "private", "cookie": "private",
                   "response": {"frequency": "daily", "total": "0", "data": []}}
        async with EIAClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )) as client:
            result = await client.fetch_national(start=DAY, end=DAY)
        meta = result.metadata.to_dict()
        attempt = meta["attempts"][0]
        body = attempt["sanitized_response"]
        self.assertEqual(attempt["response_sha256"], hashlib.sha256(body.encode()).hexdigest())
        self.assertNotIn(KEY, json.dumps(meta))
        self.assertNotIn("private", body)
        self.assertNotIn("request", json.loads(body))
        self.assertEqual(attempt["api_version"], "2.1")
        self.assertEqual(attempt["advertised_total"], "0")
        self.assertEqual(attempt["requested_length"], 5000)
        self.assertEqual(meta["sort_fields"], ["period"])

    async def test_http_api_json_and_shape_failures_have_safe_metadata(self):
        cases = [(httpx.Response(401, text=KEY), "http_error", "invalid_json"),
                 (httpx.Response(200, text=KEY), "invalid_json", "invalid_json"),
                 (httpx.Response(200, json={"error": KEY}), "api_error", "error"),
                 (httpx.Response(200, json={"response": {}}), "invalid_response", "no_error_reported")]
        for reply, code, api_status in cases:
            async with EIAClient(transport=httpx.MockTransport(lambda request: reply)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national(start=DAY, end=DAY)
            meta = caught.exception.metadata
            self.assertEqual(meta.error_code, code)
            self.assertEqual(meta.pages_fetched, 0)
            self.assertEqual(meta.retries, 0)
            self.assertEqual(meta.attempts[0].api_status, api_status)
            if api_status == "invalid_json":
                self.assertIsNone(meta.attempts[0].response_sha256)
                self.assertIsNone(meta.attempts[0].sanitized_response)
            self.assertNotIn(KEY, json.dumps(meta.to_dict()))

    async def test_transport_failure_records_actual_attempts(self):
        def handler(request):
            raise httpx.ReadError(KEY, request=request)
        with patch("trinity.connector.client.sleep", new_callable=AsyncMock):
            async with EIAClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national(start=DAY, end=DAY)
        meta = caught.exception.metadata
        self.assertEqual(meta.retries, 2)
        self.assertEqual(len(meta.attempts), 3)
        self.assertTrue(all(a.http_status is None for a in meta.attempts))
        self.assertTrue(all(a.error_code == "transport_error" for a in meta.attempts))
        self.assertNotIn(KEY, json.dumps(meta.to_dict()))

    async def test_deadline_in_backoff_does_not_count_unstarted_retry(self):
        async def block(delay):
            await asyncio.Event().wait()
        with patch("trinity.connector.client.sleep", side_effect=block):
            async with EIAClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
                with self.assertRaises(EIAClientError) as caught:
                    await client.fetch_national(start=DAY, end=DAY, timeout_seconds=0.01)
        meta = caught.exception.metadata
        self.assertEqual(meta.error_code, "pagination_deadline")
        self.assertEqual(meta.retries, 0)
        self.assertEqual(len(meta.attempts), 1)

    async def test_deadline_during_request_records_interruption(self):
        async def handler(request):
            await asyncio.Event().wait()
        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(EIAClientError) as caught:
                await client.fetch_national(start=DAY, end=DAY, timeout_seconds=0.01)
        meta = caught.exception.metadata
        self.assertEqual(meta.error_code, "pagination_deadline")
        self.assertEqual(meta.attempts[0].error_code, "interrupted")
        self.assertIsNone(meta.attempts[0].http_status)

    async def test_invalid_arguments_and_unexpected_errors(self):
        async with EIAClient(transport=httpx.MockTransport(lambda request: response([], 0))) as client:
            with self.assertRaises(EIAInputError) as caught:
                await client.fetch_national(start=DAY, end=DAY, page_size=0)
        self.assertEqual(caught.exception.metadata.error_code, "invalid_arguments")
        self.assertEqual(caught.exception.metadata.attempts, ())
        def handler(request):
            raise RuntimeError(KEY)
        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(EIAClientError) as caught:
                await client.fetch_national(start=DAY, end=DAY)
        self.assertEqual(caught.exception.metadata.error_code, "unexpected_error")
        self.assertNotIn(KEY, json.dumps(caught.exception.metadata.to_dict()))

    async def test_concurrent_calls_keep_counters_separate(self):
        def handler(request):
            return httpx.Response(401) if "facility-nuclear" in request.url.path else response([], 0)
        async with EIAClient(transport=httpx.MockTransport(handler)) as client:
            results = await asyncio.gather(client.fetch_national(start=DAY, end=DAY),
                                           client.fetch_facility(start=DAY, end=DAY), return_exceptions=True)
        self.assertEqual(results[0].metadata.dataset, "national")
        self.assertEqual(results[0].metadata.pages_fetched, 1)
        self.assertEqual(results[1].metadata.dataset, "facility")
        self.assertEqual(results[1].metadata.pages_fetched, 0)
        self.assertEqual(len(results[0].metadata.attempts), 1)
        self.assertEqual(len(results[1].metadata.attempts), 1)

    async def test_orchestrator_continues_after_failure_with_one_client(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(401) if "facility-nuclear" in request.url.path else response([], 0)
        emitted = []
        with patch("trinity.connector.pipeline.EIAClient", wraps=EIAClient) as factory:
            results = await retrieve_all(start=DAY, end=DAY, on_result=emitted.append,
                                         transport=httpx.MockTransport(handler))
        self.assertEqual(factory.call_count, 1)
        self.assertEqual([r.metadata.dataset for r in results], list(DATASETS))
        self.assertEqual([r.metadata.final_status for r in results], ["success", "failed", "success"])
        self.assertEqual(emitted, results)
        self.assertIsNone(results[1].collection)
        self.assertIsNotNone(results[0].collection)
        self.assertEqual(len(requests), 3)
        self.assertTrue(all(r.url.params["start"] == DAY.isoformat() for r in requests))

    async def test_missing_key_produces_three_failed_results(self):
        with patch.dict(os.environ, {}, clear=True):
            results = await retrieve_all(start=DAY, end=DAY)
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertEqual(result.metadata.error_code, "configuration_error")
            self.assertEqual(result.metadata.final_status, "failed")
            self.assertEqual(result.metadata.attempts, ())

    async def test_cancellation_records_interrupted_and_skipped_routes(self):
        started = asyncio.Event()
        async def handler(request):
            started.set()
            await asyncio.Event().wait()
        emitted = []
        task = asyncio.create_task(retrieve_all(start=DAY, end=DAY, on_result=emitted.append,
                                               transport=httpx.MockTransport(handler)))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([r.metadata.final_status for r in emitted], ["cancelled", "skipped", "skipped"])
        self.assertEqual(len(emitted[0].metadata.attempts), 1)
        self.assertEqual(emitted[1].metadata.attempts, ())


class CommandTests(unittest.TestCase):
    def args(self, path):
        return ["--start", "2026-10-01", "--end", "2026-10-01", "--output", str(path)]

    def test_configuration_failure_saves_three_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval.jsonl"
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
                code = main(self.args(path))
            saved = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(code, 1)
            self.assertEqual(len(saved), 3)
            self.assertTrue(all(r["final_status"] == "failed" for r in saved))
            self.assertEqual(len(output.getvalue().splitlines()), 3)

    def test_success_and_failure_exit_codes_with_saved_attempts(self):
        for fail in (False, True):
            def handler(request):
                return httpx.Response(401) if fail and "facility-nuclear" in request.url.path else response([], 0)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "retrieval.jsonl"
                def factory(*args, **kwargs):
                    kwargs["transport"] = httpx.MockTransport(handler)
                    return EIAClient(*args, **kwargs)
                with patch.dict(os.environ, {"EIA_API_KEY": KEY}, clear=True):
                    with patch("trinity.connector.pipeline.EIAClient", side_effect=factory):
                        with redirect_stdout(io.StringIO()):
                            code = main(self.args(path))
                saved = [json.loads(line) for line in path.read_text().splitlines()]
                self.assertEqual(code, 1 if fail else 0)
                self.assertEqual(len(saved), 3)
                self.assertTrue(all(len(r["attempts"]) == 1 for r in saved))
                self.assertNotIn(KEY, path.read_text())

    def test_existing_output_is_preserved_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval.jsonl"
            path.write_text("keep this")
            with patch("trinity.connector.__main__.retrieve_all") as run, redirect_stderr(io.StringIO()):
                code = main(self.args(path))
            run.assert_not_called()
            self.assertEqual(code, 2)
            self.assertEqual(path.read_text(), "keep this")

    def test_write_failure_is_nonzero_and_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retrieval.jsonl"
            error = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch("os.fsync", side_effect=OSError(KEY)):
                with redirect_stderr(error):
                    code = main(self.args(path))
            self.assertEqual(code, 2)
            self.assertNotIn(KEY, error.getvalue())


if __name__ == "__main__":
    unittest.main()
