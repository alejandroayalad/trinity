"""Spawn production operations with controlled crashes at publication boundaries."""
import os
import time
from pathlib import Path
from unittest.mock import patch

from trinity.adapters.postgres import Database
from trinity.config import ApiSettings, S3Settings
from trinity.adapters.s3 import S3Storage
from trinity.publication.commands import PublicationCommands
from trinity.publication.service import PublicationService
from trinity.workers.publication import PublicationWorker
from test_s3 import MemoryS3


def command_process(dsn, token, version, action, key, etag, start, output):
    """Race in independent pools and report only safe status codes."""
    db=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));db.open()
    try:
        start.wait(15)
        try:
            receipt=PublicationCommands(db).command(token,version,action,b'{}',[key],[etag])
            output.put(('accepted',str(receipt.operation_id)))
        except Exception as error:
            output.put(('rejected',getattr(error,'status',500)))
    finally:db.close()


def crash_publisher(dsn, root, payload, objects, phase, marker):
    """Kill the actual worker around claim, verification and final transaction."""
    db=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));db.open()
    memory=MemoryS3();memory.objects.update(objects)
    storage=S3Storage(S3Settings('synthetic-bucket','versions','us-east-1'),client=memory)
    worker=PublicationWorker(db,root,lambda:storage)
    original_claim=PublicationService.claim
    original_finish=PublicationService.finish
    def die():
        Path(marker).write_text(phase)
        os._exit(17)
    if phase=='before_claim':
        with patch.object(PublicationService,'claim',lambda *_:die()):worker.execute(payload)
    elif phase=='after_claim':
        def claim(*args):
            original_claim(*args);die()
        with patch.object(PublicationService,'claim',claim):worker.execute(payload)
    elif phase=='verification':
        memory.get_object=lambda **_:die()
        worker.execute(payload)
    elif phase=='before_commit':
        with patch.object(PublicationService,'finish',lambda *_:die()):worker.execute(payload)
    elif phase=='mid_commit':
        from contextlib import contextmanager
        original_transaction = PublicationService.transaction
        class Connection:
            def __init__(self, value): self.value=value
            def execute(self, statement, parameters=()):
                result=self.value.execute(statement,parameters)
                if 'UPDATE active_publication' in statement: die()
                return result
        @contextmanager
        def transaction(instance,*args,**kwargs):
            with original_transaction(instance,*args,**kwargs) as connection:
                yield Connection(connection)
        with patch.object(PublicationService,'transaction',transaction): worker.execute(payload)
    elif phase=='after_commit':
        def finish(*args):
            original_finish(*args);die()
        with patch.object(PublicationService,'finish',finish):worker.execute(payload)


def cli_process(dsn, root, run, generation, fence, start, output):
    """Run the executable from an independent process after a shared barrier."""
    import subprocess
    import sys
    import json
    start.wait(15)
    env={k:v for k,v in os.environ.items() if not k.startswith(('TRINITY_','AWS_','EIA_'))}
    env.update(TRINITY_DATABASE_URL=dsn,TRINITY_REFRESH_ROOT=root)
    result=subprocess.run([sys.executable,'-m','trinity.workers','publication-recover','--run-id',run,
        '--expected-generation',str(generation),'--expected-fence',str(fence)],env=env,capture_output=True,text=True,timeout=20)
    output.put((result.returncode,json.loads(result.stdout)['outcome']))


def crash_publication_dispatch(dsn,root,connection,name,after_enqueue):
    """Exit before acknowledgment while real Redis may already retain the job."""
    import asyncio
    from trinity.adapters.queue import PublicationQueue
    from trinity.publication.dispatch import PublicationDispatch
    db=Database(ApiSettings(TRINITY_DATABASE_URL=dsn));db.open()
    async def scenario():
        queue=PublicationQueue(connection,name=name)
        row=PublicationDispatch(db,queue,root).claim()
        if after_enqueue:await queue.enqueue(row['payload'])
        os._exit(17)
    asyncio.run(scenario())


def hold_preparation_lock(path, ready, release):
    """Model a preparation child retaining its original shared custody lock."""
    import fcntl
    with open(path, 'rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        ready.set()
        release.wait(30)
