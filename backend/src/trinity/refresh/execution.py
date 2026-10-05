"""Fence the first execution claim against duplicate queue delivery."""
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from trinity.adapters.postgres import Deadline
from trinity.adapters.queue import refresh_payload
from trinity.errors import Problem
from trinity.refresh.dispatch import fail_run
from trinity.refresh.repository import lock_control


class ExecutionService:
    """Perform short fenced transactions; no external calls occur inside SQL."""
    def __init__(self, database):
        self.database = database

    def transaction(self):
        """Bound connection and statement time for each durable transition."""
        return self.database.transaction(Deadline(), error_code='dependency_unavailable')

    def claim(self, payload, owner):
        """Return a first execution claim; duplicate or repaired-old jobs do nothing."""
        payload = refresh_payload(payload)
        run_id = UUID(payload['run_id'])
        with self.transaction() as connection:
            control = lock_control(connection)
            run = connection.execute('SELECT * FROM refresh_runs WHERE id=%s FOR UPDATE', (run_id,)).fetchone()
            outbox = connection.execute("SELECT * FROM job_outbox WHERE run_id=%s AND job_kind='refresh_pipeline' FOR UPDATE",
                                        (run_id,)).fetchone()
            if (not run or not outbox or control['holder_run_id'] != run_id
                    or run['status'] != 'requested' or run['started_at'] is not None
                    or payload != outbox['payload'] or outbox['dispatch_attempts'] < 1
                    or connection.execute('SELECT id FROM data_versions WHERE run_id=%s', (run_id,)).fetchone()):
                return None
            # A valid queue identity cannot make an unsupported stored policy
            # executable. Admission freezes these values for this implementation.
            expected = {'workflow_policy':'warnings-v1','diagnostic_registry':'warnings-v1',
                        'contract_version':'trinity-data-v1','validation_checkset':'trinity-data-v1',
                        'end_strategy':'latest_national','settings_revision':run['settings_revision'],
                        'requested_start':run['requested_start'].isoformat()}
            if any(run['policy_snapshot'].get(key) != value for key,value in expected.items()):
                fail_run(connection,run_id,'refresh_failed',stage='extract')
                return None
            return connection.execute("""UPDATE refresh_runs SET status='running',
                started_at=clock_timestamp(),execution_fence=execution_fence+1,revision=revision+1,
                worker_owner_id=%s,lease_until=clock_timestamp()+interval '30 seconds',
                execution_deadline_at=clock_timestamp()+interval '1530 seconds'
                WHERE id=%s RETURNING *""", (owner,run_id)).fetchone()
