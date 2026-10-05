"""Retain refresh commands and queue obligations after the Preview migration chain."""
from alembic import op

revision = '0006_refresh_dispatch'
down_revision = '0005_refresh_evidence'
branch_labels = None
depends_on = None


def upgrade():
    """Create durable intent; no queue call or publication occurs in a migration."""
    op.execute("""
        CREATE TABLE job_outbox (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES refresh_runs(id),
            job_kind text NOT NULL CHECK (job_kind IN ('refresh_pipeline','publish_version')),
            deduplication_key text NOT NULL UNIQUE,
            payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','dispatching','delivered')),
            available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            dispatch_attempts bigint NOT NULL DEFAULT 0 CHECK (dispatch_attempts>=0),
            dispatch_generation bigint NOT NULL DEFAULT 0 CHECK (dispatch_generation>=0),
            lease_token uuid,
            lease_until timestamptz,
            delivered_at timestamptz,
            last_error text,
            UNIQUE(run_id,job_kind),
            CHECK ((status='dispatching' AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
                OR (status<>'dispatching' AND lease_token IS NULL AND lease_until IS NULL)),
            CHECK ((status='delivered')=(delivered_at IS NOT NULL))
        );
        CREATE INDEX refresh_outbox_pending ON job_outbox(available_at) WHERE status<>'delivered';
        CREATE TABLE api_commands (
            id uuid PRIMARY KEY,
            idempotency_key uuid NOT NULL UNIQUE,
            actor_id text NOT NULL REFERENCES local_users(id),
            action text NOT NULL,
            target_id uuid,
            request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
            accepted_at timestamptz NOT NULL,
            run_id uuid NOT NULL REFERENCES refresh_runs(id),
            version_id uuid REFERENCES data_versions(id),
            result text NOT NULL CHECK (result IN ('queued','warning_resolved','discarded')),
            status_url text NOT NULL
        );
        ALTER TABLE refresh_runs
            ADD COLUMN execution_deadline_at timestamptz,
            ADD COLUMN worker_owner_id uuid,
            ADD COLUMN worker_execution_ref jsonb
                CHECK (worker_execution_ref IS NULL OR jsonb_typeof(worker_execution_ref)='object');
        ALTER TABLE refresh_steps ADD COLUMN deadline_at timestamptz;
        CREATE FUNCTION refresh_keep_execution_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (OLD.requested_end IS NOT NULL AND
                (NEW.requested_end IS DISTINCT FROM OLD.requested_end OR
                 NEW.window_frozen_at IS DISTINCT FROM OLD.window_frozen_at)) OR
               (OLD.execution_deadline_at IS NOT NULL AND
                NEW.execution_deadline_at IS DISTINCT FROM OLD.execution_deadline_at) OR
               (OLD.started_at IS NOT NULL AND
                (NEW.started_at IS DISTINCT FROM OLD.started_at OR
                 NEW.requested_start IS DISTINCT FROM OLD.requested_start OR
                 NEW.policy_snapshot IS DISTINCT FROM OLD.policy_snapshot)) THEN
                RAISE EXCEPTION 'Immutable refresh execution bounds' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_execution_bounds BEFORE UPDATE ON refresh_runs
            FOR EACH ROW EXECUTE FUNCTION refresh_keep_execution_bounds();
        CREATE FUNCTION refresh_worker_version_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM refresh_runs r WHERE r.id=NEW.run_id
                AND r.execution_deadline_at IS NOT NULL AND
                (NEW.coverage_start IS DISTINCT FROM r.requested_start OR
                 NEW.coverage_end IS DISTINCT FROM r.requested_end OR
                 NEW.latest_observation_date IS DISTINCT FROM r.requested_end)) THEN
                RAISE EXCEPTION 'Candidate differs from frozen worker bounds' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_worker_version_bounds BEFORE INSERT OR UPDATE ON data_versions
            FOR EACH ROW EXECUTE FUNCTION refresh_worker_version_bounds();
        CREATE FUNCTION refresh_keep_step_budget() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.deadline_at IS NOT NULL AND NEW.deadline_at IS DISTINCT FROM OLD.deadline_at THEN
                RAISE EXCEPTION 'Immutable refresh step budget' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_step_budget BEFORE UPDATE ON refresh_steps
            FOR EACH ROW EXECUTE FUNCTION refresh_keep_step_budget();
    """)


def downgrade():
    """Remove this slice only when an operator selects a disposable database."""
    op.execute("""
        DROP TRIGGER refresh_worker_version_bounds ON data_versions;
        DROP FUNCTION refresh_worker_version_bounds();
        DROP TRIGGER refresh_execution_bounds ON refresh_runs;
        DROP FUNCTION refresh_keep_execution_bounds();
        DROP TRIGGER refresh_step_budget ON refresh_steps;
        DROP FUNCTION refresh_keep_step_budget();
        ALTER TABLE refresh_steps DROP COLUMN deadline_at;
        ALTER TABLE refresh_runs DROP COLUMN execution_deadline_at,DROP COLUMN worker_owner_id,
            DROP COLUMN worker_execution_ref;
        DROP TABLE api_commands,job_outbox;
    """)
