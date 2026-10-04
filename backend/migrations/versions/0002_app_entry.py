"""Create the canonical state dependency closure for app-entry reads."""
from alembic import op

revision = "0002_app_entry"
down_revision = "0001_local_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create empty shared state; this grants no publication authority."""
    op.execute("""
        CREATE TABLE shared_settings (
            id integer PRIMARY KEY CHECK (id=1),
            setup_completed_at timestamptz,
            schedule_enabled boolean NOT NULL DEFAULT false,
            daily_time text CHECK (daily_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
            schedule_timezone text,
            revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_by text REFERENCES local_users(id),
            CHECK ((setup_completed_at IS NULL AND NOT schedule_enabled AND daily_time IS NULL
                    AND schedule_timezone IS NULL AND updated_by IS NULL)
                OR (setup_completed_at IS NOT NULL AND daily_time IS NOT NULL
                    AND schedule_timezone IS NOT NULL AND updated_by IS NOT NULL))
        );
        CREATE TABLE refresh_runs (
            id uuid PRIMARY KEY,
            run_seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE CHECK (run_seq>0),
            revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0),
            rerun_of_run_id uuid REFERENCES refresh_runs(id),
            publication_generation bigint NOT NULL DEFAULT 0 CHECK (publication_generation>=0),
            trigger_kind text NOT NULL CHECK (trigger_kind IN ('manual','scheduled','rerun')),
            requested_by text REFERENCES local_users(id),
            request_key uuid NOT NULL UNIQUE,
            requested_at timestamptz NOT NULL,
            started_at timestamptz,
            finished_at timestamptz,
            status text NOT NULL CHECK (status IN ('requested','running','awaiting_approval','publishing',
                                                 'publication_failed','succeeded','failed','discarded','superseded')),
            settings_revision bigint NOT NULL CHECK (settings_revision>=0),
            policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot)='object'),
            requested_start date NOT NULL,
            requested_end date,
            window_frozen_at timestamptz,
            execution_fence bigint NOT NULL DEFAULT 0 CHECK (execution_fence>=0),
            lease_until timestamptz,
            error_code text,
            error_summary text,
            CHECK ((trigger_kind='scheduled') = (requested_by IS NULL)),
            CHECK ((requested_end IS NULL) = (window_frozen_at IS NULL)),
            CHECK (requested_end IS NULL OR requested_end>=requested_start),
            CHECK ((status IN ('succeeded','failed','discarded','superseded')) = (finished_at IS NOT NULL)),
            CHECK (status<>'failed' OR (error_code IS NOT NULL AND error_summary IS NOT NULL))
        );
        CREATE TABLE refresh_steps (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES refresh_runs(id),
            step_seq bigint NOT NULL CHECK (step_seq>0),
            stage text NOT NULL CHECK (stage IN ('extract','prepare','validate','publish')),
            work_key text NOT NULL,
            attempt bigint NOT NULL CHECK (attempt>=1),
            status text NOT NULL CHECK (status IN ('pending','running','succeeded','failed','abandoned')),
            execution_fence bigint NOT NULL CHECK (execution_fence>=0),
            started_at timestamptz,
            finished_at timestamptz,
            heartbeat_at timestamptz,
            processed_count bigint NOT NULL DEFAULT 0 CHECK (processed_count>=0),
            total_count bigint CHECK (total_count>=0),
            progress_unit text NOT NULL CHECK (progress_unit IN ('rows','files','checks','tasks')),
            error_code text,
            error_summary text,
            UNIQUE (run_id, step_seq), UNIQUE (run_id, stage, work_key, attempt),
            CHECK ((status IN ('succeeded','failed','abandoned')) = (finished_at IS NOT NULL))
        );
        CREATE TABLE data_versions (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL UNIQUE REFERENCES refresh_runs(id),
            revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0),
            status text NOT NULL CHECK (status IN ('preparing','validating','validated','rejected')),
            disposition text NOT NULL CHECK (disposition IN ('active','discarded','superseded')),
            discarded_at timestamptz,
            discarded_by text REFERENCES local_users(id),
            approval_required boolean,
            review_warning_count bigint CHECK (review_warning_count>=0),
            review_warning_digest text CHECK (review_warning_digest ~ '^[0-9a-f]{64}$'),
            diagnostics_frozen_at timestamptz,
            created_at timestamptz NOT NULL,
            manifest_frozen_at timestamptz,
            manifest_sha256 text CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            validated_at timestamptz,
            validation_step_id uuid REFERENCES refresh_steps(id),
            coverage_start date NOT NULL,
            coverage_end date NOT NULL,
            latest_observation_date date NOT NULL,
            contract_version text NOT NULL,
            validation_checkset text NOT NULL,
            CHECK (coverage_start<=latest_observation_date AND latest_observation_date<=coverage_end),
            CHECK ((disposition='discarded' AND discarded_at IS NOT NULL AND discarded_by IS NOT NULL)
                OR (disposition<>'discarded' AND discarded_at IS NULL AND discarded_by IS NULL)),
            CHECK ((diagnostics_frozen_at IS NULL AND approval_required IS NULL
                    AND review_warning_count IS NULL AND review_warning_digest IS NULL)
                OR (diagnostics_frozen_at IS NOT NULL AND approval_required IS NOT NULL
                    AND review_warning_count IS NOT NULL AND review_warning_digest IS NOT NULL
                    AND approval_required=(review_warning_count>0))),
            CHECK (status NOT IN ('validating','validated')
                OR (manifest_sha256 IS NOT NULL AND manifest_frozen_at IS NOT NULL)),
            CHECK (status<>'validated' OR (validated_at IS NOT NULL AND validation_step_id IS NOT NULL
                AND diagnostics_frozen_at IS NOT NULL))
        );
        CREATE TABLE approvals (
            id uuid PRIMARY KEY,
            version_id uuid NOT NULL UNIQUE REFERENCES data_versions(id),
            approved_by text NOT NULL REFERENCES local_users(id),
            approved_at timestamptz NOT NULL,
            manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            validation_step_id uuid NOT NULL REFERENCES refresh_steps(id),
            review_warning_digest text NOT NULL CHECK (review_warning_digest ~ '^[0-9a-f]{64}$')
        );
        CREATE TABLE publication_events (
            id uuid PRIMARY KEY,
            version_id uuid NOT NULL UNIQUE REFERENCES data_versions(id),
            previous_publication_event_id uuid REFERENCES publication_events(id),
            approval_id uuid REFERENCES approvals(id),
            published_at timestamptz NOT NULL,
            publication_mode text NOT NULL CHECK (publication_mode IN ('automatic','approval')),
            actor_id text REFERENCES local_users(id),
            idempotency_key uuid NOT NULL UNIQUE,
            CHECK ((publication_mode='automatic' AND approval_id IS NULL AND actor_id IS NULL)
                OR (publication_mode='approval' AND approval_id IS NOT NULL AND actor_id IS NOT NULL))
        );
        CREATE TABLE active_publication (
            id integer PRIMARY KEY CHECK (id=1),
            publication_event_id uuid REFERENCES publication_events(id),
            revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0)
        );
        CREATE TABLE refresh_control (
            id integer PRIMARY KEY CHECK (id=1),
            holder_run_id uuid REFERENCES refresh_runs(id),
            revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0)
        );
        CREATE TABLE failure_warnings (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES refresh_runs(id),
            version_id uuid REFERENCES data_versions(id),
            stage text NOT NULL CHECK (stage IN ('extract','prepare','validate','publish')),
            code text NOT NULL,
            message text NOT NULL,
            created_at timestamptz NOT NULL,
            resolved_at timestamptz,
            resolution text CHECK (resolution IN ('rerun','delete_warning','publication_retry','discard','superseded')),
            resolved_by text REFERENCES local_users(id),
            CHECK ((resolved_at IS NULL AND resolution IS NULL AND resolved_by IS NULL)
                OR (resolved_at IS NOT NULL AND resolution IS NOT NULL
                    AND ((resolution='superseded' AND resolved_by IS NULL)
                        OR (resolution<>'superseded' AND resolved_by IS NOT NULL))))
        );
        CREATE UNIQUE INDEX one_unresolved_warning ON failure_warnings ((true)) WHERE resolved_at IS NULL;
        INSERT INTO shared_settings(id) VALUES (1);
        INSERT INTO active_publication(id) VALUES (1);
        INSERT INTO refresh_control(id) VALUES (1);
    """)


def downgrade() -> None:
    """Remove the dependency closure only in a disposable database."""
    op.execute("""DROP TABLE failure_warnings, refresh_control, active_publication,
        publication_events, approvals, data_versions, refresh_steps, refresh_runs, shared_settings""")
