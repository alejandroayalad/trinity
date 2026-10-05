"""Carry refresh notifications; PostgreSQL remains the authority for execution."""
import asyncio
from uuid import UUID

from bullmq import Queue, Worker


def refresh_payload(value):
    """Reject untrusted queue fields before loading any protected run state."""
    keys = {'schema_version', 'run_id', 'version_id', 'job_kind', 'dispatch_generation'}
    if (not isinstance(value, dict) or set(value) != keys
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['job_kind'] != 'refresh_pipeline' or value['version_id'] is not None
            or type(value['dispatch_generation']) is not int or value['dispatch_generation'] < 0):
        raise ValueError('invalid_refresh_notification')
    if str(UUID(value['run_id'])) != value['run_id']:
        raise ValueError('invalid_refresh_notification')
    return dict(value)


def job_id(payload):
    """Use a colon-free BullMQ ID; repair generations bypass retained old jobs."""
    data = refresh_payload(payload)
    return f"refresh-{data['run_id']}-{data['dispatch_generation']}"


class RefreshQueue:
    """Use the selected BullMQ Redis adapter with bounded transport calls.

    Library retries cannot authorize another pipeline. Each notification carries
    only identity and generation. The consumer reloads all execution inputs from
    PostgreSQL. Retain completed jobs so deduplication behavior remains explicit.
    """
    def __init__(self, connection, *, name='trinity-refresh', timeout=10):
        self.connection, self.name, self.timeout = connection, name, timeout
        self.queue = Queue(name, {'connection': connection})

    async def enqueue(self, payload):
        """Enqueue outside the outbox transaction; an ambiguous timeout may duplicate."""
        async with asyncio.timeout(self.timeout):
            return await self.queue.add('refresh_pipeline', refresh_payload(payload), {
                'jobId': job_id(payload), 'attempts': 1,
                'removeOnComplete': False, 'removeOnFail': False,
            })

    async def state(self, payload):
        """Read transport state only; a retained job is not proof of execution."""
        async with asyncio.timeout(self.timeout):
            return await self.queue.getJobState(job_id(payload))

    def consumer(self, processor):
        """Create one consumer; the processor must enforce the database claim."""
        return Worker(self.name, processor, {'connection': self.connection, 'concurrency': 1})

    async def close(self):
        """Release this adapter's own Redis connection."""
        await self.queue.close()
