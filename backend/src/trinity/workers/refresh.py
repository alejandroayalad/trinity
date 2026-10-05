"""Consume one fenced refresh with existing supervised preparation.

Trusted configuration supplies source/storage settings and an owner-only durable
root. PostgreSQL supplies the accepted policy. Discovery freezes the date and
version before the first extraction. One child runs preparation; its events are
journaled and committed before acknowledgment. On failure, retain only measured
validation rows and keep the lifecycle blocked. A completed receipt is retained
and verified before atomic candidate registration. Registration queues publication
or waits for review; it never activates data.
"""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import fcntl
import os
from pathlib import Path
import socket
from uuid import UUID, uuid4

from trinity.adapters.s3 import S3Storage
from trinity.connector import parquet, prepare
from trinity.connector.validate import _bound_results, REQUIRED_CHECKS, DIAGNOSTIC_CHECKS
from trinity.connector.client import EIAClient
from trinity.connector.pipeline import _read_storage_file
from trinity.contracts.manifest import read_json, sha256
from trinity.refresh.evidence import _results
from trinity.refresh.execution import ExecutionService
from trinity.refresh.registration import CandidateRegistration


def partial_results(root, attempt):
    """Load only complete journal lines with matching immutable detail bytes.

    A killed write can leave a final incomplete line. Earlier completed lines
    remain evidence. This loader grants no success and never fills absent checks.
    """
    if root is None or attempt is None:
        return ()
    from uuid import UUID
    prefix = f'evidence/{UUID(attempt)}'
    items = []
    seen = set()
    try:
        with parquet._directory(root) as descriptor:
            paths = parquet._inventory(descriptor)
            if f'{prefix}/journal.jsonl' not in paths:
                return ()
            raw = _read_storage_file(descriptor, f'{prefix}/journal.jsonl')
            for line in raw.splitlines(keepends=True):
                if not line.endswith(b'\n'):
                    break
                event = read_json(line)
                if event.get('event') != 'result':
                    continue
                result, = _results([event['result']])
                pair = (result.check_code,result.dataset_key)
                if (pair in seen or pair not in (*REQUIRED_CHECKS,*DIAGNOSTIC_CHECKS)
                        or not _bound_results((result,),(pair,),version_id=root.name,attempt_id=attempt,
                            manifest_sha256=result.manifest_sha256,required=pair in REQUIRED_CHECKS)
                        or result.checked_count > 9223372036854775807
                        or result.version_id != root.name or result.attempt_id != attempt
                        or result.details_path != f'{prefix}/{result.check_code}-{result.dataset_key}.json'
                        or _read_storage_file(descriptor,result.details_path) != result.details_json):
                    raise ValueError('invalid_partial_evidence')
                seen.add(pair)
                items.append(result)
    except FileNotFoundError:
        return ()
    return tuple(items)


def failure_results(root, attempt):
    """Keep corrupt files on disk, but never import their unverified row claims.

    This loader is used only to terminate a confirmed stopped execution as failed.
    A malformed or altered journal cannot keep that run indefinitely running.
    Missing or rejected evidence supplies no results and grants no readiness.
    """
    try:
        return partial_results(root, attempt)
    except Exception:
        return ()


def register_receipt(database, run, root, storage_factory):
    """Use only durable custody and the remaining original execution budget.

    The caller holds the process lifetime lock. Registration separately checks
    the database fence before and after remote verification. No new extraction,
    reserved version, validation attempt or receipt hash is created here.
    """
    ref = run['worker_execution_ref']
    remaining = (run['execution_deadline_at']-datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ValueError('registration_deadline_exhausted')
    return CandidateRegistration(database).register(run_id=run['id'],
        version_id=UUID(ref['version_id']),step_id=UUID(ref['validation_step_id']),
        fence=run['execution_fence'],root=root,receipt_sha256=ref['receipt_sha256'],
        storage=storage_factory(),timeout_seconds=min(30,remaining))


class RefreshWorker:
    """Coordinate one claim; duplicate notifications cannot launch another child."""
    def __init__(self, database, output_root, eia, s3, *, worker=prepare._worker,
                 discovery_transport=None, limits=prepare.Limits(), cancelled=lambda:False,
                 storage_factory=None):
        self.execution = ExecutionService(database)
        self.output_root = Path(output_root).resolve(strict=True)
        self.eia, self.s3 = eia, s3
        self.worker, self.discovery_transport, self.limits = worker, discovery_transport, limits
        self.cancelled = cancelled
        self.storage_factory = storage_factory or (lambda:S3Storage(self.s3))

    async def _discover(self, run, event, heartbeat):
        """Keep discovery within its budget and renew the independent worker lease."""
        event({'event':'started','stage':'discovery'})
        async with EIAClient(self.eia, transport=self.discovery_transport,
                before_attempt=lambda data:event({'event':'attempt',**data})) as client:
            task = asyncio.create_task(client.discover_latest(start=run['requested_start']))
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=5)
                    heartbeat()
                return await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    def execute(self, payload):
        """Run a first claim synchronously; the BullMQ adapter calls it in a thread."""
        owner = uuid4()
        run = self.execution.claim(payload,owner)
        if run is None:
            return 'ignored'
        run_id, fence = run['id'], run['execution_fence']
        event = lambda value:self.execution.event(run_id,owner,fence,value)
        def heartbeat():
            if self.cancelled():
                raise prepare.PreparationError('supervisor','cancelled')
            self.execution.heartbeat(run_id,owner,fence)
        reference = lambda value, **kw:self.execution.reference(run_id,owner,fence,value,**kw)
        # The supervisor and child hold this inode for their complete lifetimes.
        # Recovery uses the same trusted root and an exclusive, nonblocking lock.
        lock_path = self.output_root / f'{run_id}.lock'
        descriptor = None
        root = None
        try:
            descriptor = os.open(lock_path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            fcntl.flock(descriptor,fcntl.LOCK_SH)
            reference({'host':socket.gethostname(),'owner':str(owner),'child_stopped':False,
                       'lock_inode':os.fstat(descriptor).st_ino})
            end, discovery = asyncio.run(self._discover(run,event,heartbeat))
            version = self.execution.freeze(run_id,owner,fence,end,discovery)
            event({'event':'finished','stage':'discovery','status':'success'})
            root = prepare._reserve(self.output_root,run['requested_start'],end,version_id=version['id'])
            reference({'version_id':str(version['id']),'pipeline_started':True})
            remaining = (run['execution_deadline_at']-datetime.now(UTC)).total_seconds()
            limits = replace(self.limits,overall=min(self.limits.overall,remaining))
            code,result = prepare.supervise({'root':root,'start':run['requested_start'],'end':end,
                'eia':self.eia,'s3':self.s3,'durable_hooks':True,'ownership_lock':str(lock_path)},
                worker=self.worker,limits=limits,on_event=event,heartbeat=heartbeat,
                on_spawn=lambda pid:reference({'child_pid':pid}))
            if result.get('error_code') == 'child_exit_unconfirmed':
                return 'stop_unconfirmed'
            ref = reference({'child_stopped':True},stopped=True)
            if code == 0:
                # Reuse the supervisor's original digest. The verifier checks
                # local and remote bytes before the database grants readiness.
                if sha256((root/prepare.EVIDENCE/'result.json').read_bytes()) != ref.get('receipt_sha256'):
                    raise ValueError('changed_receipt')
                ref = reference({'preparation_complete':True})
                heartbeat()
                return register_receipt(self.execution.database,
                    {**run,'worker_execution_ref':ref},root,self.storage_factory)
            rows = failure_results(root,ref.get('validation_attempt_id'))
            failure = 'stage_timeout' if result.get('error_code') == 'deadline_exceeded' else 'refresh_failed'
            self.execution.fail(run_id,owner,fence,failure,results=rows)
            return 'failed'
        except Exception:
            # supervise confirms exit before returning/raising. If persistence
            # is unavailable, keep the lease/blocker for same-host recovery.
            try:
                ref = reference({'child_stopped':True},stopped=True)
                rows = failure_results(root,ref.get('validation_attempt_id'))
                self.execution.fail(run_id,owner,fence,'refresh_failed',results=rows)
                return 'failed'
            except Exception:
                pass
            return 'retained'
        finally:
            if descriptor is not None:
                os.close(descriptor)

    async def process(self, job, _token):
        """Keep BullMQ's event loop free to maintain its own transport lock."""
        return await asyncio.to_thread(self.execute,job.data)
