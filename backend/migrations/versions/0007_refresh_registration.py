"""Keep receipt verification budgets across worker crashes and recovery."""
from alembic import op

revision = '0007_refresh_registration'
down_revision = '0006_refresh_dispatch'
branch_labels = None
depends_on = None


def upgrade():
    """Add nullable historical budgets without altering retained evidence."""
    op.execute("""
        ALTER TABLE refresh_runs
            ADD COLUMN registration_deadline_at timestamptz,
            ADD COLUMN registration_attempts integer NOT NULL DEFAULT 0
                CHECK (registration_attempts BETWEEN 0 AND 3),
            ADD CONSTRAINT registration_within_execution CHECK
                (registration_deadline_at IS NULL OR execution_deadline_at IS NULL
                 OR registration_deadline_at<=execution_deadline_at);
        CREATE FUNCTION refresh_keep_registration_budget() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (OLD.registration_deadline_at IS NOT NULL AND
                NEW.registration_deadline_at IS DISTINCT FROM OLD.registration_deadline_at)
                OR NEW.registration_attempts<OLD.registration_attempts THEN
                RAISE EXCEPTION 'Immutable registration budget' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_registration_budget BEFORE UPDATE ON refresh_runs
            FOR EACH ROW EXECUTE FUNCTION refresh_keep_registration_budget();
    """)


def downgrade():
    """Remove only this additive budget schema from an operator-selected database."""
    op.execute("""
        DROP TRIGGER refresh_registration_budget ON refresh_runs;
        DROP FUNCTION refresh_keep_registration_budget();
        ALTER TABLE refresh_runs DROP CONSTRAINT registration_within_execution,
            DROP COLUMN registration_deadline_at,DROP COLUMN registration_attempts;
    """)
