"""Reuse bounded outbox transport without automatic publication crash recovery."""
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from trinity.refresh.dispatch import DispatchService, MAX_ATTEMPTS
from trinity.publication.service import locked, fail_stopped
from trinity.publication.custody import custody, CustodyError


class PublicationDispatch(DispatchService):
    """Dispatch only unacknowledged publishing intent, never delivered jobs."""
    def __init__(self, database, queue, root):
        super().__init__(database,queue)
        self.root = Path(root)

    def claim(self):
        """Persist one transport attempt; exhausted unclaimed work needs stop proof."""
        # Context managers close right to left. Commit SQL before ExitStack
        # closes the acquired process lock, including on an exception.
        with ExitStack() as custody_stack, self.transaction() as c:
            control = c.execute('SELECT holder_run_id FROM refresh_control WHERE id=1').fetchone()
            if not control or not control['holder_run_id']:
                return None
            control,run,version,_ = locked(c,control['holder_run_id'])
            if run['status']!='publishing' or not version:
                return None
            step = c.execute("SELECT id FROM refresh_steps WHERE run_id=%s AND stage='publish' AND attempt=%s",
                             (run['id'],run['publication_generation']+1)).fetchone()
            if step:
                return None
            row = c.execute("""SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='publish_version'
                AND status<>'delivered' AND available_at<=clock_timestamp()
                AND (lease_until IS NULL OR lease_until<=clock_timestamp()) FOR UPDATE""",(run['id'],)).fetchone()
            if not row:
                return None
            # Preparation can still own the original lock after registration.
            # Prove it released custody before consuming any transport attempt.
            try:
                custody_stack.enter_context(custody(self.root,run))
            except CustodyError:
                return None
            if row['dispatch_attempts']>=MAX_ATTEMPTS:
                fail_stopped(c,run,version,'publication_dispatch_exhausted')
                return None
            return c.execute("""UPDATE job_outbox SET status='dispatching',lease_token=%s,
                lease_until=clock_timestamp()+interval '60 seconds',dispatch_attempts=dispatch_attempts+1
                WHERE id=%s RETURNING *""",(uuid4(),row['id'])).fetchone()

    async def recover(self):
        """Delivered publication loss requires explicit operator reconciliation."""
        return False
