"""Dispatch committed refresh intent and repair missing notifications.

Claim a database lease and persist each attempt before Redis access. Acknowledge
only the same token and generation. Recovery can repair transport for a requested
run, but can never create another run or restart a claimed pipeline. Publication
obligations belong to the later publisher and are excluded here.
"""
from uuid import uuid4

from psycopg.types.json import Jsonb
from trinity.adapters.postgres import Deadline
from trinity.refresh.repository import lock_control


MAX_ATTEMPTS = 3


def fail_run(connection, run_id, code, *, stage='prepare'):
    """Retain the occupied slot and one safe warning on a locked failed run."""
    connection.execute("""UPDATE refresh_runs SET status='failed',finished_at=clock_timestamp(),
        revision=revision+1,lease_until=NULL,error_code=%s,error_summary='Refresh could not complete.'
        WHERE id=%s""", (code, run_id))
    connection.execute("""INSERT INTO failure_warnings(id,run_id,version_id,stage,code,message,created_at)
        VALUES(%s,%s,(SELECT id FROM data_versions WHERE run_id=%s),%s,%s,
        'Refresh could not complete.',clock_timestamp())""", (uuid4(),run_id,run_id,stage,code))


class DispatchService:
    """Keep bounded dispatch accounting durable across process restarts."""
    def __init__(self, database, queue):
        self.database, self.queue = database, queue

    def transaction(self):
        """Use short database transactions; never hold one during Redis calls."""
        return self.database.transaction(Deadline(), error_code='dependency_unavailable')

    def claim(self):
        """Claim one due intent, or fail exhausted intent that no worker owns."""
        with self.transaction() as connection:
            control = lock_control(connection)
            run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE',
                                     (control['holder_run_id'],)).fetchone()
            if not run or run['status'] != 'requested':
                return None
            row = connection.execute("""SELECT * FROM job_outbox WHERE run_id=%s
                AND job_kind='refresh_pipeline' AND status<>'delivered'
                AND available_at<=clock_timestamp()
                AND (lease_until IS NULL OR lease_until<=clock_timestamp()) FOR UPDATE""",
                (run['id'],)).fetchone()
            if row is None:
                return None
            if row['dispatch_attempts'] >= MAX_ATTEMPTS:
                fail_run(connection, run['id'], 'dispatch_failed')
                return None
            token = uuid4()
            return connection.execute("""UPDATE job_outbox SET status='dispatching',lease_token=%s,
                lease_until=clock_timestamp()+interval '60 seconds',dispatch_attempts=dispatch_attempts+1
                WHERE id=%s RETURNING *""", (token,row['id'])).fetchone()

    def acknowledge(self, row, *, succeeded):
        """A stale dispatcher cannot acknowledge a repaired generation or lease."""
        with self.transaction() as connection:
            lock_control(connection)
            return connection.execute("""UPDATE job_outbox SET status=%s,
                delivered_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,
                available_at=clock_timestamp()+(CASE WHEN dispatch_attempts=1 THEN 1 ELSE 3 END)*interval '1 second',
                lease_token=NULL,lease_until=NULL,last_error=%s
                WHERE id=%s AND status='dispatching' AND lease_token=%s AND dispatch_generation=%s
                AND lease_until>clock_timestamp() RETURNING id""",
                ('delivered' if succeeded else 'pending',succeeded,None if succeeded else 'queue_unavailable',
                 row['id'],row['lease_token'],row['dispatch_generation'])).fetchone() is not None

    async def once(self):
        """Attempt one persisted obligation; a crash leaves its lease recoverable."""
        row = self.claim()
        if row is None:
            return False
        try:
            await self.queue.enqueue(row['payload'])
        except Exception:
            self.acknowledge(row, succeeded=False)
        else:
            self.acknowledge(row, succeeded=True)
        return True

    async def recover(self):
        """Repair lost or terminal notifications only while execution is unclaimed."""
        with self.transaction() as connection:
            row = connection.execute("""SELECT o.* FROM job_outbox o JOIN refresh_runs r ON r.id=o.run_id
                WHERE o.job_kind='refresh_pipeline' AND o.status='delivered' AND r.status='requested'
                AND o.delivered_at<=clock_timestamp()-interval '10 seconds'""").fetchone()
        if row is None:
            return False
        state = await self.queue.state(row['payload'])
        if state not in ('unknown', 'completed', 'failed'):
            return False
        with self.transaction() as connection:
            control = lock_control(connection)
            run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE', (row['run_id'],)).fetchone()
            current = connection.execute('SELECT * FROM job_outbox WHERE id=%s FOR UPDATE', (row['id'],)).fetchone()
            if (control['holder_run_id'] != row['run_id'] or run['status'] != 'requested'
                    or current['status'] != 'delivered'
                    or current['dispatch_generation'] != row['dispatch_generation']):
                return False
            if current['dispatch_attempts'] >= MAX_ATTEMPTS:
                fail_run(connection, run['id'], 'dispatch_failed')
                return False
            generation = current['dispatch_generation'] + 1
            payload = {**current['payload'], 'dispatch_generation': generation}
            connection.execute("""UPDATE job_outbox SET status='pending',delivered_at=NULL,
                dispatch_generation=%s,payload=%s,available_at=clock_timestamp() WHERE id=%s""",
                (generation,Jsonb(payload),row['id']))
            return True
