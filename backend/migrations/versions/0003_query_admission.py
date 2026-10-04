"""Persist rolling analytical rate limits and fenced query reservations."""
from alembic import op

revision = "0003_query_admission"
down_revision = "0002_app_entry"
branch_labels = None
depends_on = None


def upgrade():
    """Add empty admission state without changing retained publications."""
    op.execute("""
        CREATE TABLE analytical_rate_limits (
            user_id text PRIMARY KEY REFERENCES local_users(id),
            admitted_at timestamptz[] NOT NULL DEFAULT '{}',
            last_time timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (cardinality(admitted_at)<=30)
        );
        CREATE TABLE query_admission (id integer PRIMARY KEY CHECK (id=1));
        INSERT INTO query_admission(id) VALUES(1);
        CREATE TABLE query_reservations (
            request_id uuid PRIMARY KEY,
            user_id text NOT NULL REFERENCES local_users(id),
            publication_event_id uuid NOT NULL REFERENCES publication_events(id),
            version_id uuid NOT NULL REFERENCES data_versions(id),
            manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            deployment_id uuid NOT NULL,
            daemon_id text NOT NULL,
            owner_token uuid NOT NULL,
            generation bigint NOT NULL DEFAULT 1 CHECK (generation>0),
            state text NOT NULL CHECK (state IN ('reserved','staging','creating','created',
                'starting','running','stopping','cleaning','released')),
            container_name text NOT NULL UNIQUE,
            container_id text UNIQUE,
            start_intent boolean NOT NULL DEFAULT false,
            deadline timestamptz NOT NULL,
            heartbeat_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            released_at timestamptz,
            outcome text CHECK (outcome IN ('succeeded','query_failed','query_timeout',
                'query_resource_limit','dependency_unavailable','cancelled')),
            cleanup_complete boolean NOT NULL DEFAULT false,
            CHECK ((state='released') = (released_at IS NOT NULL)),
            CHECK (NOT start_intent OR container_id IS NOT NULL)
        );
        CREATE INDEX query_active_user ON query_reservations(user_id) WHERE state<>'released';
        CREATE INDEX query_recovery ON query_reservations(deployment_id,deadline) WHERE state<>'released';
    """)


def downgrade():
    """Remove query state only under explicit disposable-database authority."""
    op.execute("DROP TABLE query_reservations,query_admission,analytical_rate_limits")
