"""Run a selected background role from trusted process configuration.

Refresh requires the EIA/storage settings and can perform external work. Operators
must complete setup and deployment gates before enabling roles for retained data.
Publication verifies registered evidence and activates it atomically. Its outbox
and operator recovery modes load no EIA key and never activate publication.
The scheduler admits due daily occurrences in PostgreSQL only; it loads no
EIA key, S3 credential or Redis URL.
"""
import argparse
import asyncio
import os
import signal
import sys

from trinity.adapters.postgres import Database
from trinity.adapters.queue import RefreshQueue, PublicationQueue
from trinity.config import load_api_settings, load_eia_settings, load_s3_settings
from trinity.refresh.dispatch import DispatchService
from trinity.workers import outbox, recovery
from trinity.workers.refresh import RefreshWorker


async def serve(role):
    """Own resources and close them when the process receives a stop signal."""
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for signum in (signal.SIGINT,signal.SIGTERM):
        loop.add_signal_handler(signum,stop.set)
    database=Database(load_api_settings())
    queue=None
    consumer=None
    database.open()
    try:
        if role=='scheduler':
            # The scheduler only writes PostgreSQL rows. Branch before any
            # Redis, EIA or S3 setting is read, so the role starts with
            # TRINITY_DATABASE_URL alone and cannot do external work.
            from trinity.workers import scheduler
            scheduler.configure_logging()
            await scheduler.run(scheduler.SchedulerService(database),stop)
            return
        if role in ('publication','publication-outbox'):
            from trinity.publication.dispatch import PublicationDispatch
            from trinity.workers.publication import PublicationWorker
            from trinity.adapters.s3 import S3Storage
            queue=PublicationQueue(os.environ['TRINITY_REDIS_URL'])
            if role=='publication-outbox':
                await outbox.run(PublicationDispatch(database,queue,os.environ['TRINITY_REFRESH_ROOT']),stop)
            else:
                worker=PublicationWorker(database,os.environ['TRINITY_REFRESH_ROOT'],lambda:S3Storage(load_s3_settings()))
                consumer=queue.consumer(worker.process)
                await stop.wait()
            return
        queue=RefreshQueue(os.environ['TRINITY_REDIS_URL'])
        dispatch=DispatchService(database,queue)
        if role=='outbox':
            await outbox.run(dispatch,stop)
        elif role=='recovery':
            await recovery.run(dispatch,recovery.RecoveryService(database,os.environ['TRINITY_REFRESH_ROOT'],load_s3_settings()),stop)
        else:
            worker=RefreshWorker(database,os.environ['TRINITY_REFRESH_ROOT'],load_eia_settings(),load_s3_settings(),
                                 cancelled=stop.is_set)
            consumer=queue.consumer(worker.process)
            await stop.wait()
    finally:
        if consumer is not None:
            await consumer.close()
        if queue is not None:
            await queue.close()
        database.close()


def main(argv=None):
    """Select a fixed role; expose no exception text or secret-bearing settings."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0]=='publication-recover':
        from trinity.publication.recovery import cli
        return cli(arguments[1:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=('outbox','refresh','recovery','publication','publication-outbox',
                                        'publication-recover','scheduler'))
    args=parser.parse_args(arguments)
    try:
        asyncio.run(serve(args.role))
        return 0
    except Exception:
        print('Worker stopped: configuration or dependency unavailable.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
