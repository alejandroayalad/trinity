"""Exercise real synthetic evidence verification with bounded concurrent callers.

No test reads S3 or retained state. Events hold the first bundle read so tests
can arrange overlap, cancellation and failure without relying on network speed.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from trinity.auth.permissions import Principal
from trinity.errors import Problem
from trinity.publication.diagnostics import read_verified_diagnostics
from trinity.publication.evidence_cache import EvidenceCache
from trinity.queries.service import PreviewService, QueryDeadline
from trinity.queries.staging import PublishedReader
from test_preview_provenance import frozen_fixture
from test_preview_service import Database
from test_preview_unit import codec
from test_sql_staging import Client

NAMESPACE = ('deployment', 'synthetic', 'versions', 'test-region', 'read-profile')


class GateReader(PublishedReader):
    """Hold the first read until permitted, while checking the shared deadline."""

    def __init__(self, objects):
        super().__init__(Client(objects), SimpleNamespace(bucket='synthetic', prefix='versions'))
        self.entered, self.proceed = threading.Event(), threading.Event()

    def read_into(self, *args, **kwargs):
        self.entered.set()
        while not self.proceed.wait(0.005):
            kwargs['deadline'].remaining()
        return super().read_into(*args, **kwargs)


def wait_for_callers(cache, count):
    """Arrange overlap by checking registration, not by sleeping for a guess."""
    end = time.monotonic() + 2
    while time.monotonic() < end:
        with cache._condition:
            if sum(len(entry.callers) for entry in cache._entries.values()) >= count:
                return
        time.sleep(0.001)
    raise AssertionError('Concurrent callers did not register')


class EvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.pinned, self.objects = frozen_fixture()
        self.cache = EvidenceCache()
        self.reader = PublishedReader(Client(self.objects), SimpleNamespace(bucket='synthetic', prefix='versions'))

    def read(self, dataset='national', *, cache=None, reader=None, pinned=None, deadline=None, namespace=NAMESPACE):
        return (cache or self.cache).read(pinned or self.pinned, dataset, reader or self.reader,
                                         deadline or QueryDeadline(30), namespace=namespace)

    def assert_timeout(self, future):
        with self.assertRaises(Problem) as caught:
            future.result(timeout=2)
        self.assertEqual((caught.exception.status, caught.exception.code), (504, 'query_timeout'))

    def test_hit_reuses_evidence_across_datasets_but_returns_independent_scoped_notes(self):
        national = self.read()
        self.assertEqual([note.code for note in national], ['D02'])
        national[0].affected_count = '999'
        national.clear()
        facility = self.read('facility')
        self.assertEqual([(note.code, note.scope) for note in facility], [('D01', 'facility')])
        self.assertEqual(self.read('generator'), [])
        self.assertEqual(self.read()[0].affected_count, '1')
        self.assertEqual(len(self.reader.client.calls), 3)
        entry = next(iter(self.cache._entries.values()))
        self.assertIsInstance(entry.summaries, tuple)
        self.assertNotIn('PRIVATE_DETAIL', repr(entry.summaries))
        self.assertNotIn('D09', repr(entry.summaries))
        # A restarted/different process starts empty; there is no shared disk cache.
        self.read(cache=EvidenceCache())
        self.assertEqual(len(self.reader.client.calls), 6)

    def test_expiry_is_fixed_from_success_and_never_extended_by_hits(self):
        clock = Mock(return_value=0.0)
        cache = EvidenceCache(clock=clock)
        original = self.reader.read_into

        def advances(*args, **kwargs):
            clock.return_value = 10.0
            return original(*args, **kwargs)

        with patch.object(self.reader, 'read_into', side_effect=advances):
            self.read(cache=cache)
        for now in (59.0, 69.999):
            clock.return_value = now
            self.read(cache=cache)
        self.assertEqual(len(self.reader.client.calls), 3)
        clock.return_value = 70.0
        self.read(cache=cache)
        self.assertEqual(len(self.reader.client.calls), 6)

    def test_sixteen_entry_bound_evicts_least_recently_used_completed_identity(self):
        pins = [replace(self.pinned, publication=self.pinned.publication.model_copy(
            update={'publication_event_id': uuid4()})) for _ in range(17)]
        for pinned in pins[:16]:
            self.read(pinned=pinned)
        self.read(pinned=pins[0])
        self.read(pinned=pins[16])
        self.assertEqual(len(self.cache._entries), 16)
        self.assertEqual(len(self.reader.client.calls), 51)
        self.read(pinned=pins[1])
        self.assertEqual(len(self.reader.client.calls), 54)

    def test_every_publication_evidence_field_and_namespace_is_part_of_identity(self):
        # This isolates cache identity from verifier rejection of altered pins.
        # The real verifier remains covered by the provenance tests and below.
        changes = {
            'manifest_sha256': 'b' * 64, 'contract_version': 'other',
            'evidence_bundle_sha256': 'c' * 64, 'validation_attempt_id': str(uuid4()),
            'validation_checkset': 'other', 'review_warning_digest': 'd' * 64,
            'review_warning_count': 0, 'approval_required': False,
        }
        public_changes = {
            'publication_event_id': uuid4(), 'version_id': uuid4(),
            'published_at': self.pinned.publication.published_at + timedelta(seconds=1),
            'coverage_start': self.pinned.publication.coverage_start - timedelta(days=1),
            'coverage_end': self.pinned.publication.coverage_end + timedelta(days=1),
            'latest_observation_date': self.pinned.publication.latest_observation_date - timedelta(days=1),
        }
        with patch('trinity.publication.evidence_cache.read_verified_diagnostics', return_value=()) as verify:
            self.read()
            for name, value in changes.items():
                self.read(pinned=replace(self.pinned, **{name: value}))
            for name, value in public_changes.items():
                self.read(pinned=replace(self.pinned, publication=self.pinned.publication.model_copy(update={name: value})))
            for index in range(len(NAMESPACE)):
                namespace = tuple('different' if i == index else item for i, item in enumerate(NAMESPACE))
                self.read(namespace=namespace)
            self.assertEqual(verify.call_count, 1 + len(changes) + len(public_changes) + len(NAMESPACE))

    def test_corrupt_evidence_and_expired_fill_failure_never_use_old_result(self):
        clock = Mock(return_value=0.0)
        cache = EvidenceCache(clock=clock)
        self.read(cache=cache)
        self.objects['bundle.json'] += b'changed'
        clock.return_value = 60.0
        for _ in range(2):
            with self.assertRaises(Problem) as caught:
                self.read(cache=cache)
            self.assertEqual(caught.exception.code, 'dependency_unavailable')
        self.assertEqual(len(cache._entries), 0)
        self.assertEqual(len(self.reader.client.calls), 5)
        self.objects['bundle.json'] = self.objects['bundle.json'][:-7]
        self.read(cache=cache)
        self.assertEqual(len(self.reader.client.calls), 8)

    def test_cancelled_or_expired_hit_and_unknown_dataset_are_rejected(self):
        self.read()
        cancelled = QueryDeadline(30)
        cancelled.cancelled = threading.Event()
        cancelled.cancelled.set()
        for deadline in (cancelled, QueryDeadline(-1)):
            with self.assertRaises(Problem) as caught:
                self.read(deadline=deadline)
            self.assertEqual(caught.exception.code, 'query_timeout')
        with self.assertRaises(Problem):
            self.read('unknown')
        self.assertEqual(len(self.reader.client.calls), 3)

    def test_concurrent_cold_reads_verify_and_download_once_including_other_datasets(self):
        reader = GateReader(self.objects)
        with patch('trinity.publication.evidence_cache.read_verified_diagnostics', wraps=read_verified_diagnostics) as verify:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(self.read, scope, reader=reader)
                           for scope in ('national', 'facility', 'generator', 'national')]
                try:
                    self.assertTrue(reader.entered.wait(2))
                    wait_for_callers(self.cache, 4)
                finally:
                    reader.proceed.set()
                results = [future.result(timeout=2) for future in futures]
            self.assertEqual(verify.call_count, 1)
        self.assertEqual(len(reader.client.calls), 3)
        self.assertEqual([[note.scope for note in notes] for notes in results],
                         [['national'], ['facility'], [], ['national']])

    def test_concurrent_failure_is_shared_then_a_later_request_can_recover(self):
        reader = GateReader(self.objects)
        original = self.objects['bundle.json']
        self.objects['bundle.json'] += b'changed'
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(self.read, reader=reader) for _ in range(3)]
            try:
                self.assertTrue(reader.entered.wait(2))
                wait_for_callers(self.cache, 3)
            finally:
                reader.proceed.set()
            for future in futures:
                with self.assertRaises(Problem) as caught:
                    future.result(timeout=2)
                self.assertEqual(caught.exception.code, 'dependency_unavailable')
        self.assertEqual(len(reader.client.calls), 1)
        self.objects['bundle.json'] = original
        self.read(reader=reader)
        self.assertEqual(len(reader.client.calls), 4)

    def test_cancelled_waiter_leaves_while_owner_continues(self):
        reader = GateReader(self.objects)
        deadline = QueryDeadline(30)
        deadline.cancelled = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(self.read, reader=reader)
            try:
                self.assertTrue(reader.entered.wait(2))
                waiter = pool.submit(self.read, reader=reader, deadline=deadline)
                wait_for_callers(self.cache, 2)
                deadline.cancelled.set()
                self.assert_timeout(waiter)
                self.assertFalse(owner.done())
            finally:
                reader.proceed.set()
            self.assertEqual(owner.result(timeout=2)[0].code, 'D02')
        self.assertEqual(len(reader.client.calls), 3)

    def test_cancelled_owner_keeps_shared_work_alive_for_waiter_then_returns_cancellation(self):
        reader = GateReader(self.objects)
        deadline = QueryDeadline(30)
        deadline.cancelled = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(self.read, reader=reader, deadline=deadline)
            try:
                self.assertTrue(reader.entered.wait(2))
                waiter = pool.submit(self.read, 'facility', reader=reader)
                wait_for_callers(self.cache, 2)
                deadline.cancelled.set()
                # The owner still owns the reader while it serves this waiter.
                self.assertFalse(owner.done())
            finally:
                reader.proceed.set()
            self.assert_timeout(owner)
            self.assertEqual(waiter.result(timeout=2)[0].code, 'D01')
        self.read(reader=reader)
        self.assertEqual(len(reader.client.calls), 3)

    def test_all_callers_cancel_stop_the_fill_without_creating_an_entry(self):
        reader = GateReader(self.objects)
        deadlines = [QueryDeadline(30), QueryDeadline(30)]
        for deadline in deadlines:
            deadline.cancelled = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(self.read, reader=reader, deadline=deadlines[0])
            try:
                self.assertTrue(reader.entered.wait(2))
                waiter = pool.submit(self.read, reader=reader, deadline=deadlines[1])
                wait_for_callers(self.cache, 2)
                for deadline in deadlines:
                    deadline.cancelled.set()
                self.assert_timeout(waiter)
                self.assert_timeout(owner)
            finally:
                reader.proceed.set()
        self.assertEqual(len(self.cache._entries), 0)
        self.assertEqual(reader.client.calls, [])

    def test_fill_deadline_is_not_extended_by_a_later_waiter(self):
        reader = GateReader(self.objects)
        clock = Mock(return_value=0.0)
        cache = EvidenceCache(clock=clock)
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(self.read, cache=cache, reader=reader, deadline=QueryDeadline(1))
            try:
                self.assertTrue(reader.entered.wait(2))
                waiter = pool.submit(self.read, cache=cache, reader=reader)
                wait_for_callers(cache, 2)
                clock.return_value = 2.0
                self.assert_timeout(owner)
                self.assert_timeout(waiter)
            finally:
                reader.proceed.set()
        self.assertEqual(len(cache._entries), 0)

    def test_full_pending_cache_waits_without_launching_unbounded_fills(self):
        reader = GateReader(self.objects)
        cache = EvidenceCache(max_entries=1)
        other = replace(self.pinned, publication=self.pinned.publication.model_copy(update={'publication_event_id': uuid4()}))
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner = pool.submit(self.read, cache=cache, reader=reader)
            try:
                self.assertTrue(reader.entered.wait(2))
                denied = pool.submit(self.read, cache=cache, reader=reader, pinned=other, deadline=QueryDeadline(0.1))
                self.assert_timeout(denied)
                self.assertEqual(len(cache._entries), 1)
            finally:
                reader.proceed.set()
            owner.result(timeout=2)
        self.assertEqual(len(reader.client.calls), 3)


class WarmEvidenceAdmissionTests(unittest.TestCase):
    def test_warm_evidence_does_not_skip_current_authority_pin_rate_or_capacity(self):
        pinned, objects = frozen_fixture()
        reader = PublishedReader(Client(objects), SimpleNamespace(bucket='synthetic', prefix='versions'))
        cache = EvidenceCache()
        user = Principal('synthetic', 'analyst', uuid4())
        execution = Mock(deployment_id=uuid4(), daemon_id='synthetic')
        execution.execute.side_effect = lambda prepared: cache.read(
            prepared.pinned, prepared.query.dataset, reader, prepared.deadline, namespace=NAMESPACE)
        service = PreviewService(Database(), lambda: execution, codec_factory=codec)
        with patch('trinity.queries.service.resolve_session', return_value=user) as authorize, \
                patch('trinity.queries.service.read_pinned_publication', return_value=pinned) as pin, \
                patch('trinity.publication.repository.read_preview_publication', return_value=pinned), \
                patch('trinity.queries.service.repository.reserve_rate', return_value=None) as rate, \
                patch('trinity.queries.service.repository.reserve_capacity', return_value={'request_id': uuid4()}) as capacity:
            for _ in range(2):
                self.assertEqual(service.execute('synthetic-token', 'facility_outages', [])[0].scope, 'facility')
            self.assertEqual(len(reader.client.calls), 3)
            self.assertEqual((authorize.call_count, pin.call_count, rate.call_count, capacity.call_count), (4, 2, 2, 2))

            authorize.return_value = replace(user, role='viewer')
            notes = service.execute('viewer-token', 'national_outages', [])
            self.assertEqual([(note.code, note.scope) for note in notes], [('D02', 'national')])
            execution.execute.reset_mock()
            for role in ('viewer', 'unknown'):
                authorize.return_value = replace(user, role=role)
                with self.assertRaises(Problem):
                    service.execute('synthetic-token', 'facility_outages', [])
            authorize.side_effect = Problem(401, 'invalid_session')
            with self.assertRaises(Problem):
                service.execute('revoked-token', 'national_outages', [])
            authorize.side_effect = None
            authorize.return_value = user
            capacity.return_value = None
            with self.assertRaises(Problem) as caught:
                service.execute('synthetic-token', 'national_outages', [])
            self.assertEqual(caught.exception.code, 'rate_limited')
            execution.execute.assert_not_called()
            self.assertEqual(len(reader.client.calls), 3)


class EvidenceFactoryTests(unittest.TestCase):
    def test_production_requests_share_cache_but_recovery_and_transports_do_not(self):
        from trinity.queries import config
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'TRINITY_QUERY_STAGE_ROOT': str(Path(directory).resolve()),
            'TRINITY_QUERY_DEPLOYMENT_ID': str(uuid4()),
            'TRINITY_QUERY_READ_PROFILE': 'synthetic-reader',
            'TRINITY_S3_BUCKET': 'synthetic-bucket', 'TRINITY_S3_PREFIX': 'versions',
            'TRINITY_S3_REGION': 'us-east-1', 'TRINITY_DOCKER_SOCKET': '/synthetic/socket',
            'TRINITY_QUERY_IMAGE': 'synthetic-image', 'TRINITY_QUERY_STAGE_VOLUME': 'synthetic-volume',
        }), patch.object(config, 'Docker'), patch.object(config.boto3, 'Session') as session:
            first, second = config.execution_factory(Mock()), config.execution_factory(Mock())
            recovery = config.execution_factory(Mock(), recovery=True)
            self.assertIs(first.evidence_cache, config.EVIDENCE_CACHE)
            self.assertIs(first.evidence_cache, second.evidence_cache)
            self.assertIsNot(first.reader, second.reader)
            self.assertEqual(first.evidence_namespace, second.evidence_namespace)
            self.assertEqual(first.evidence_namespace[-1], 'synthetic-reader')
            self.assertIsNone(recovery.evidence_cache)
            self.assertIsNone(recovery.reader)
            self.assertEqual(session.call_count, 2)
