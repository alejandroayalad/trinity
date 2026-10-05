"""Reconcile transport and stopped executions without replaying preparation."""
import asyncio
import fcntl
import os
from pathlib import Path
import socket

from trinity.refresh.execution import ExecutionService
from trinity.workers.refresh import failure_results


class RecoveryService:
    """Confirm same-host lifetime-lock release before failing an incomplete run.

    An unknown host, missing lock, changed inode or held lock keeps admission
    blocked. A completed receipt remains available for the candidate import gate.
    Recovery never launches extraction and never discards existing evidence.
    """
    def __init__(self, database, output_root):
        self.execution = ExecutionService(database)
        self.output_root = Path(output_root).resolve(strict=True)

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
            # Recheck under SQL locks after obtaining exclusive process custody.
            with self.execution.transaction() as connection:
                current = self.execution.owned(connection,run['id'],run['worker_owner_id'],run['execution_fence'],stopped=True)
                if current['live']:
                    return 'renewed'
            if ref.get('receipt_sha256'):
                # Step 5 must verify parent completion, immutable files and the
                # original deadline. Receipt presence alone grants no readiness.
                return 'receipt_pending'
            self.execution.reference(run['id'],run['worker_owner_id'],run['execution_fence'],
                                     {'child_stopped':True},stopped=True)
            root = self.output_root/ref['version_id'] if ref.get('version_id') else None
            rows = failure_results(root,ref.get('validation_attempt_id'))
            self.execution.fail(run['id'],run['worker_owner_id'],run['execution_fence'],'worker_lost',results=rows)
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
