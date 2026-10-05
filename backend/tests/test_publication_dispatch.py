"""Use real Redis transport with production PostgreSQL and publication workers."""
import asyncio
import os
import multiprocessing
import unittest
from uuid import uuid4
from unittest.mock import patch
from postgres_fixture import DSN
from publication_fixture import PublicationFixture
from publication_process_fixture import crash_publication_dispatch, hold_preparation_lock
from trinity.adapters.queue import PublicationQueue
from trinity.publication.dispatch import PublicationDispatch

PORT=os.environ.get('TRINITY_TEST_REDIS_PORT')

@unittest.skipUnless(DSN and PORT,'Disposable PostgreSQL and Redis required')
class PublicationDispatchTests(PublicationFixture,unittest.TestCase):
    def test_unacknowledged_enqueue_duplicate_consumption_and_lost_delivered_job(self):
        async def scenario():
            queue=PublicationQueue({'host':'127.0.0.1','port':int(PORT)},name='pub-test-'+uuid4().hex)
            dispatch=PublicationDispatch(self.database,queue,self.root)
            consumer=None
            try:
                context=multiprocessing.get_context('spawn')
                for after_enqueue in (False,True):
                    process=context.Process(target=crash_publication_dispatch,args=(
                        DSN,str(self.root),queue.connection,queue.name,after_enqueue))
                    process.start();process.join(15)
                    if process.is_alive():process.kill();process.join();self.fail('dispatcher did not exit')
                    self.assertEqual(process.exitcode,17)
                    if not after_enqueue:
                        row=self.sql("SELECT * FROM job_outbox WHERE run_id=%s",(self.run,))[0]
                    self.sql("UPDATE job_outbox SET lease_until=now()-interval '1 second',available_at=now()")
                # Both restarts retain the original BullMQ identity. The third
                # persisted enqueue attempt must not create a second job.
                next_row=dispatch.claim();await queue.enqueue(next_row['payload'])
                self.assertFalse(dispatch.acknowledge(row,succeeded=True))
                self.assertTrue(dispatch.acknowledge(next_row,succeeded=True))
                self.assertEqual(await queue.queue.getWaitingCount(),1)
                consumer=queue.consumer(self.worker.process)
                for _ in range(100):
                    if self.row()['status']=='succeeded':break
                    await asyncio.sleep(.1)
                self.assertEqual(self.row()['status'],'succeeded')
                await consumer.close();consumer=None
                # Restarted duplicate dispatch cannot repeat verification.
                with patch('trinity.publication.service.load_candidate') as verify:
                    self.worker.execute(row['payload']);verify.assert_not_called()
                self.new_candidate(warnings=True)
                self.assertEqual(self.command('approve').status_code,202)
                row=dispatch.claim();await queue.enqueue(row['payload']);dispatch.acknowledge(row,succeeded=True)
                await queue.queue.obliterate(force=True)
                self.assertFalse(await dispatch.recover());self.assertIsNone(dispatch.claim())
                run=self.row()
                code,value=self.operator('--expected-generation','0','--expected-fence',str(run['execution_fence']))
                self.assertEqual((code,value['outcome']),(0,'recovered_failure'))
                self.assertEqual(self.command('publication-retry').status_code,202)
                self.assertTrue(await dispatch.once())
                consumer=queue.consumer(self.worker.process)
                for _ in range(100):
                    if self.row()['status']=='succeeded':break
                    await asyncio.sleep(.1)
                self.assertEqual(self.row()['status'],'succeeded')
            finally:
                if consumer:await consumer.close()
                await queue.queue.obliterate(force=True);await queue.close()
        asyncio.run(scenario())

    def test_three_transport_attempts_then_stop_proof_failure(self):
        async def scenario():
            queue=PublicationQueue({'host':'127.0.0.1','port':int(PORT)},name='pub-test-'+uuid4().hex)
            dispatch=PublicationDispatch(self.database,queue,self.root)
            try:
                for _ in range(3):
                    row=dispatch.claim();self.assertIsNotNone(row)
                    dispatch.acknowledge(row,succeeded=False)
                    self.sql('UPDATE job_outbox SET available_at=now()')
                self.assertIsNone(dispatch.claim())
                self.assertEqual(self.row()['status'],'publication_failed')
                self.assertEqual(self.sql('SELECT dispatch_attempts FROM job_outbox')[0]['dispatch_attempts'],3)
                self.assertEqual(self.command('publication-retry').status_code,202)
                self.assertTrue(await dispatch.once())
                self.assertIsNotNone(self.worker.execute(self.payload()))
            finally:
                await queue.queue.obliterate(force=True);await queue.close()
        asyncio.run(scenario())

    def test_preparation_lock_defers_without_consuming_attempt(self):
        # Registration can finish before the preparation child closes its lock.
        # A real independent holder must leave all three enqueue attempts intact.
        context=multiprocessing.get_context('spawn')
        ready,release=context.Event(),context.Event()
        holder=context.Process(target=hold_preparation_lock,
            args=(str(self.root/f'{self.run}.lock'),ready,release))
        holder.start()
        try:
            self.assertTrue(ready.wait(10))
            dispatch=PublicationDispatch(self.database,None,self.root)
            for _ in range(4):self.assertIsNone(dispatch.claim())
            row=self.sql('SELECT * FROM job_outbox WHERE run_id=%s',(self.run,))[0]
            self.assertEqual(row['dispatch_attempts'],0)
            self.assertEqual(row['status'],'pending')
            self.assertEqual(self.row()['status'],'publishing')
        finally:
            release.set();holder.join(10)
            if holder.is_alive():holder.kill();holder.join()
        self.assertEqual(holder.exitcode,0)
        self.assertEqual(dispatch.claim()['dispatch_attempts'],1)
