"""Index immutable saved evidence without publishing or backfilling a candidate."""
from alembic import op

revision = '0004_preview_evidence'
down_revision = '0003_query_admission'
branch_labels = None
depends_on = None


def upgrade():
    """Leave existing versions unbound until the publication writer verifies evidence."""
    op.execute("""
        ALTER TABLE data_versions
            ADD COLUMN evidence_bundle_sha256 text,
            ADD COLUMN validation_attempt_id uuid,
            ADD CONSTRAINT preview_evidence_binding CHECK (
                (evidence_bundle_sha256 IS NULL AND validation_attempt_id IS NULL)
                OR (evidence_bundle_sha256 IS NOT NULL AND validation_attempt_id IS NOT NULL
                    AND evidence_bundle_sha256 ~ '^[0-9a-f]{64}$'));
    """)


def downgrade():
    """Remove only the preview evidence index."""
    op.execute("""
        ALTER TABLE data_versions DROP CONSTRAINT preview_evidence_binding,
            DROP COLUMN validation_attempt_id, DROP COLUMN evidence_bundle_sha256;
    """)
