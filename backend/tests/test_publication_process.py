"""Exercise separate-process races, actual worker death and operator reconciliation."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import threading
import unittest
from uuid import uuid4
from unittest.mock import patch

from postgres_fixture import DSN
from publication_fixture import PublicationFixture
from publication_process_fixture import command_process, crash_publisher, cli_process
from trinity.publication.service import PublicationService

@unittest.skipUnless(DSN,'Disposable PostgreSQL required')
class PublicationProcessTests(PublicationFixture,unittest.TestCase):
    def race(self, target, args):
        """Release independent processes together and bound fixture cleanup."""
        context=multiprocessing.get_context('spawn');start=context.Event();output=context.Queue()
        processes=[context.Process(target=target,args=(*item,start,output)) for item in args]
        try:
            for process in processes:process.start()
            start.set()
            for process in processes:
                process.join(25);self.assertFalse(process.is_alive());self.assertEqual(process.exitcode,0)
            return [output.get(timeout=2) for _ in processes]
        finally:
            for process in processes:
                if process.is_alive():process.kill();process.join()

    def test_approval_and_retry_command_races(self):
        self.worker.execute(self.payload())
        for first,second in (('approve','approve'),('approve','discard'),
                             ('publication_retry','publication_retry'),('publication_retry','discard')):
            with self.subTest(first=first,second=second):
                self.new_candidate(warnings=first=='approve')
                if first=='publication_retry':
                    PublicationService(self.database).claim(self.payload());self.expire()
                    self.operator('--expected-generation','0','--expected-fence',str(self.row()['execution_fence']))
                etag=f'"candidate-{self.sql("SELECT revision FROM data_versions WHERE id=%s",(self.version,))[0]["revision"]}"'
                args=[(DSN,self.admin['Authorization'][7:],str(self.version),action,str(uuid4()),etag) for action in (first,second)]
                values=self.race(command_process,args)
                self.assertEqual(sum(value[0]=='accepted' for value in values),1,values)
                if self.row()['status']=='publishing':self.worker.execute(self.payload())

    def test_actual_crashes_reconcile_without_reinvocation(self):
        context=multiprocessing.get_context('spawn')
        for index,phase in enumerate(('before_claim','after_claim','verification','before_commit','mid_commit','after_commit')):
            with self.subTest(phase=phase):
                if index:self.new_candidate()
                marker=self.root/f'{phase}.marker'
                process=context.Process(target=crash_publisher,args=(DSN,str(self.root),self.payload(),
                    self.storage.client.objects,phase,str(marker)))
                process.start();process.join(20)
                if process.is_alive():process.kill();process.join();self.fail('crash fixture timed out')
                self.assertEqual(process.exitcode,17);self.assertTrue(marker.exists())
                if phase!='before_claim' and phase!='after_commit':
                    with patch('trinity.publication.service.load_candidate') as verifier:
                        self.worker.execute(self.payload());verifier.assert_not_called()
                if phase!='after_commit':self.expire()
                row=self.row();args=('--expected-generation','0','--expected-fence',str(row['execution_fence']))
                code,result=self.operator(*args);self.assertEqual(code,0,result)
                if phase=='after_commit':
                    self.assertEqual(result['outcome'],'already_published')
                else:
                    self.assertEqual(result['outcome'],'recovered_failure')
                    self.assertEqual(self.command('publication-retry').status_code,202)
                    self.assertIsNotNone(self.worker.execute(self.payload()))

    def test_concurrent_operators_have_one_effect(self):
        PublicationService(self.database).claim(self.payload());self.expire();row=self.row()
        args=(DSN,str(self.root),str(self.run),0,row['execution_fence'])
        values=self.race(cli_process,[args,args])
        self.assertEqual(sum(value[1]=='recovered_failure' for value in values),1,values)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM failure_warnings')[0]['n'],1)

    def test_live_thread_keeps_lock_after_lease_expiry(self):
        # Advance the durable lease while the storage call still runs. This
        # simulates cooperative timeout, which must not count as process exit.
        entered=threading.Event();release=threading.Event()
        original=self.storage.client.get_object
        def blocked(**kwargs):
            entered.set();release.wait(20)
            return original(**kwargs)
        self.storage.client.get_object=blocked
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.worker.execute,self.payload())
            self.assertTrue(entered.wait(5));self.expire();row=self.row()
            try:
                code,result=self.operator('--expected-generation','0','--expected-fence',str(row['execution_fence']))
                self.assertEqual((code,result['reason_code']),(3,'lock_held'))
            finally:release.set()
            future.result(timeout=10)
        self.assertNotEqual(self.row()['status'],'succeeded')

    def test_cancelled_async_wrapper_does_not_release_live_thread_lock(self):
        import asyncio
        from types import SimpleNamespace
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        original=self.storage.client.get_object
        def blocked(**kwargs):
            entered.set();release.wait(20)
            return original(**kwargs)
        self.storage.client.get_object=blocked
        async def scenario():
            task=asyncio.create_task(self.worker.process(SimpleNamespace(data=self.payload()),None))
            while not entered.is_set():await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.expire();run=self.row()
            try:
                code,value=self.operator('--expected-generation','0','--expected-fence',str(run['execution_fence']))
                self.assertEqual((code,value['reason_code']),(3,'lock_held'))
            finally:release.set()
        asyncio.run(scenario())
        self.assertNotEqual(self.row()['status'],'succeeded')
