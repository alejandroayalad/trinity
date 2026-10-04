"""Create local identities, revocable sessions and shared login counters."""
from alembic import op

revision = "0001_local_auth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create authentication state without provisioning passwords."""
    op.execute("""
        CREATE TABLE local_users (
            id text PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 128),
            username text NOT NULL UNIQUE CHECK (length(username) BETWEEN 1 AND 128),
            password_hash text NOT NULL,
            role text NOT NULL CHECK (role IN ('viewer','analyst','admin')),
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE TABLE local_sessions (
            id uuid PRIMARY KEY,
            user_id text NOT NULL REFERENCES local_users(id),
            token_digest text NOT NULL UNIQUE CHECK (token_digest ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CHECK (expires_at > created_at),
            CHECK (revoked_at IS NULL OR revoked_at >= created_at)
        );
        CREATE INDEX local_sessions_user_idx ON local_sessions(user_id);
        CREATE INDEX local_sessions_expiry_idx ON local_sessions(expires_at);
        CREATE TABLE auth_login_limits (
            scope text NOT NULL CHECK (scope IN ('global','peer','username')),
            key_digest text NOT NULL CHECK (key_digest ~ '^[0-9a-f]{64}$'),
            window_start timestamptz NOT NULL,
            attempts bigint NOT NULL CHECK (attempts >= 0),
            PRIMARY KEY (scope, key_digest)
        );
        CREATE INDEX auth_login_limits_window_idx ON auth_login_limits(window_start);
    """)


def downgrade() -> None:
    """Remove only this revision; use solely on disposable databases."""
    op.execute("DROP TABLE auth_login_limits, local_sessions, local_users")
