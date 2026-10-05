"""Verify selected BullMQ against real disposable Redis and PostgreSQL."""
import asyncio
import os
import multiprocessing
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock

from postgres_fixture import DSN, PostgresFixture
from trinity.adapters.queue import RefreshQueue, job_id
from trinity.refresh.dispatch import DispatchService
from trinity.refresh.execution import ExecutionService

PORT=os.environ.get('TRINITY_TEST_REDIS_PORT')


def crash_dispatch(dsn, connection, name, after_enqueue):
    """Die without cleanup at a real outbox/Redis boundary."""
    from trinity.adapters.postgres import Database
    from trinity.config import ApiSettings
    database=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));database.open()
    async def scenario():
        queue=RefreshQueue(connection,name=name)
        row=DispatchService(database,queue).claim()
        if after_enqueue:
            await queue.enqueue(row['payload'])
        os._exit(8)
    asyncio.run(scenario())


@unittest.skipUnless(DSN and PORT,'Use run_local_refresh_checks.py for real Redis and PostgreSQL')
class DispatchTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.setup_done()
        response=self.client.post('/api/v1/refresh-runs',json={},headers={**self.login('admin'),'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code,202,response.text)
        self.connection={'host':'127.0.0.1','port':int(PORT),'socket_connect_timeout':2,'socket_timeout':2}
        self.queue_name='test-'+uuid4().hex

    def outbox(self):
        return self.sql("SELECT * FROM job_outbox WHERE job_kind='refresh_pipeline'")[0]

    def expire_dispatch(self):
        self.sql("UPDATE job_outbox SET lease_until=now()-interval '1 second',available_at=now() WHERE status='dispatching'")

    def test_crash_before_and_after_enqueue_stale_ack_and_duplicate_claim(self):
        async def scenario():
            queue=RefreshQueue(self.connection,name=self.queue_name)
            dispatch=DispatchService(self.database,queue)
            try:
                context=multiprocessing.get_context('spawn')
                for after_enqueue in (False,True):
                    process=context.Process(target=crash_dispatch,args=(DSN,self.connection,self.queue_name,after_enqueue))
                    process.start();process.join(15)
                    if process.is_alive():
                        process.kill();process.join();self.fail('dispatcher did not exit')
                    self.assertEqual(process.exitcode,8)
                    if not after_enqueue:
                        before=self.outbox()
                        self.expire_dispatch()
                # Simulate process death without acknowledgment: the same job
                # remains in Redis, while the database lease later expires.
                self.expire_dispatch()
                final=dispatch.claim()
                await queue.enqueue(final['payload'])
                self.assertFalse(dispatch.acknowledge(before,succeeded=True))
                self.assertTrue(dispatch.acknowledge(final,succeeded=True))
                self.assertEqual(await queue.queue.getWaitingCount(),1)
                self.assertEqual(self.outbox()['dispatch_attempts'],3)
                execution=ExecutionService(self.database)
                owner=uuid4()
                self.assertIsNotNone(execution.claim(final['payload'],owner))
                self.assertIsNone(execution.claim(final['payload'],uuid4()))
                self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],1)
            finally:
                await queue.queue.obliterate(force=True);await queue.close()
        asyncio.run(scenario())

    def test_queue_loss_and_retained_completed_job_use_new_generation(self):
        async def scenario():
            queue=RefreshQueue(self.connection,name=self.queue_name)
            dispatch=DispatchService(self.database,queue)
            consumer=None
            try:
                await dispatch.once()
                original=self.outbox()['payload']
                # Complete a retained notification without claiming SQL. A
                # repaired generation must not be suppressed by that old ID.
                consumed=asyncio.Event()
                async def acknowledge_only(job,token):
                    consumed.set()
                consumer=queue.consumer(acknowledge_only)
                await asyncio.wait_for(consumed.wait(),10)
                for _ in range(100):
                    if await queue.state(original)=='completed':break
                    await asyncio.sleep(.02)
                await consumer.close();consumer=None
                self.assertEqual(await queue.state(original),'completed')
                self.sql("UPDATE job_outbox SET delivered_at=now()-interval '11 seconds'")
                self.assertTrue(await dispatch.recover())
                await dispatch.once()
                repaired=self.outbox()['payload']
                self.assertEqual(repaired['dispatch_generation'],1)
                self.assertNotEqual(job_id(original),job_id(repaired))
                self.assertIsNone(ExecutionService(self.database).claim(original,uuid4()))
                job=await queue.queue.getJob(job_id(repaired));await job.remove()
                self.sql("UPDATE job_outbox SET delivered_at=now()-interval '11 seconds'")
                self.assertTrue(await dispatch.recover())
                await dispatch.once()
                self.assertIsNotNone(ExecutionService(self.database).claim(self.outbox()['payload'],uuid4()))
                self.assertEqual(self.sql('SELECT count(*) AS n FROM refresh_runs')[0]['n'],1)
            finally:
                if consumer:await consumer.close()
                await queue.queue.obliterate(force=True);await queue.close()
        asyncio.run(scenario())

    def test_real_unavailable_redis_exhaustion_retains_failure_and_slot(self):
        async def scenario():
            queue=RefreshQueue({**self.connection,'port':1},name=self.queue_name,timeout=.2)
            dispatch=DispatchService(self.database,queue)
            try:
                for _ in range(3):
                    self.sql('UPDATE job_outbox SET available_at=now()')
                    self.assertTrue(await dispatch.once())
                self.sql('UPDATE job_outbox SET available_at=now()')
                self.assertFalse(await dispatch.once())
                self.assertEqual(self.sql('SELECT status FROM refresh_runs')[0]['status'],'failed')
                self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)
                self.assertIsNotNone(self.sql('SELECT holder_run_id FROM refresh_control')[0]['holder_run_id'])
            finally:
                await queue.close()
        asyncio.run(scenario())

    def test_claim_before_dispatch_failure_prevents_false_failure(self):
        async def scenario():
            queue=RefreshQueue(self.connection,name=self.queue_name)
            dispatch=DispatchService(self.database,queue)
            try:
                row=dispatch.claim()
                self.assertIsNotNone(ExecutionService(self.database).claim(row['payload'],uuid4()))
                dispatch.acknowledge(row,succeeded=False)
                self.sql('UPDATE job_outbox SET available_at=now(),dispatch_attempts=3')
                self.assertIsNone(dispatch.claim())
                self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],0)
            finally:
                await queue.close()
        asyncio.run(scenario())
