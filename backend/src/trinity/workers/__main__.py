"""Run a selected background role from trusted process configuration.

Refresh requires the EIA/storage settings and can perform external work. Operators
must complete setup and the candidate-routing gate before enabling this role for
live data. Outbox and recovery load no EIA key and never activate publication.
"""
import argparse
import asyncio
import os
import signal
import sys

from trinity.adapters.postgres import Database
from trinity.adapters.queue import RefreshQueue
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=('outbox','refresh','recovery'))
    args=parser.parse_args(argv)
    try:
        asyncio.run(serve(args.role))
        return 0
    except Exception:
        print('Worker stopped: configuration or dependency unavailable.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
