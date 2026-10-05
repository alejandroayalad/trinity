"""Reconcile transport and stopped executions without replaying preparation."""
import asyncio
import fcntl
import os
from pathlib import Path
import socket

from trinity.refresh.execution import ExecutionService
from trinity.adapters.s3 import S3Storage
from trinity.workers.refresh import failure_results, register_receipt


class RecoveryService:
    """Confirm same-host lifetime-lock release before failing an incomplete run.

    An unknown host, missing lock, changed inode or held lock keeps admission
    blocked. A completed receipt is verified under a new database fence.
    Recovery never launches extraction and never discards existing evidence.
    """
    def __init__(self, database, output_root, s3=None, *, storage_factory=None):
        self.execution = ExecutionService(database)
        self.output_root = Path(output_root).resolve(strict=True)
        self.storage_factory = storage_factory or (lambda:S3Storage(s3))

    def once(self):
        """Retain unknown execution; fail only after both process owners have ended."""
        with self.execution.transaction() as connection:
            run = connection.execute("""SELECT r.* FROM refresh_runs r JOIN refresh_control c ON c.holder_run_id=r.id
                WHERE r.status='running' AND r.lease_until<=clock_timestamp()""").fetchone()
        if not run:
            return 'idle'
        ref = run['worker_execution_ref'] or {}
        if ref.get('host') != socket.gethostname() or not ref.get('lock_inode'):
            return 'unknown_owner'
        try:
            descriptor = os.open(self.output_root/f"{run['id']}.lock",os.O_RDONLY|os.O_NOFOLLOW)
        except OSError:
            return 'unknown_owner'
        try:
            if os.fstat(descriptor).st_ino != ref['lock_inode']:
                return 'unknown_owner'
            try:
                fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                return 'still_owned'
            # Exclusive process custody proves both supervisor and child have
            # released the inode. SQL still rejects a renewed or replaced owner.
            run = self.execution.reclaim_stopped(run['id'],run['worker_owner_id'],run['execution_fence'])
            ref = run['worker_execution_ref']
            root = self.output_root/ref['version_id'] if ref.get('version_id') else None
            code = 'worker_lost'
            if ref.get('receipt_sha256'):
                try:
                    return register_receipt(self.execution.database,run,root,self.storage_factory)
                except Exception:
                    # Invalid/missing evidence or expired budgets cannot leave
                    # a confirmed stopped execution silently running forever.
                    # If SQL is unavailable the outer loop retains custody for
                    # a later bounded recovery; accepted state rejects failure.
                    code = 'refresh_failed'
            rows = failure_results(root,ref.get('validation_attempt_id'))
            self.execution.fail(run['id'],run['worker_owner_id'],run['execution_fence'],code,results=rows)
            return 'failed'
        finally:
            os.close(descriptor)


async def run(dispatch, execution, stop):
    """Poll recovery with bounded calls; unavailable persistence retains work."""
    while not stop.is_set():
        try:
            await dispatch.recover()
            await asyncio.to_thread(execution.once)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(),timeout=10)
        except TimeoutError:
            pass
