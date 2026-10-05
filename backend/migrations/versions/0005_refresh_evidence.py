"""Extend Preview's evidence index with the refresh writer's retained proof."""
from alembic import op

revision = '0005_refresh_evidence'
down_revision = '0004_preview_evidence'
branch_labels = None
depends_on = None


def upgrade():
    """Add writer records without fabricating evidence for existing versions.

    Preview already owns the candidate bundle and attempt columns. Preserve
    their bytes and nullability. A non-null preparation receipt opts a new
    writer record into the stronger selected-step binding below.
    """
    op.execute("""
        ALTER TABLE refresh_steps
            ADD COLUMN validation_attempt_id uuid UNIQUE,
            ADD COLUMN validation_sha256 text CHECK (validation_sha256 ~ '^[0-9a-f]{64}$'),
            ADD COLUMN diagnostics_sha256 text CHECK (diagnostics_sha256 ~ '^[0-9a-f]{64}$'),
            ADD CONSTRAINT validation_step_identity CHECK (
                validation_attempt_id IS NULL OR stage='validate');
        ALTER TABLE data_versions
            ADD COLUMN preparation_receipt_sha256 text
                CHECK (preparation_receipt_sha256 ~ '^[0-9a-f]{64}$'),
            ADD COLUMN storage_verified_at timestamptz,
            ADD CONSTRAINT refresh_storage_proof CHECK (
                (preparation_receipt_sha256 IS NULL AND storage_verified_at IS NULL)
                OR (preparation_receipt_sha256 IS NOT NULL AND storage_verified_at IS NOT NULL
                    AND evidence_bundle_sha256 IS NOT NULL AND validation_attempt_id IS NOT NULL
                    AND status='validated'));
        CREATE TABLE dataset_artifacts (
            id uuid PRIMARY KEY,
            version_id uuid NOT NULL REFERENCES data_versions(id),
            dataset_key text NOT NULL CHECK (dataset_key IN ('national','facility','generator')),
            storage_path text NOT NULL CHECK (storage_path ~ '^data/[A-Za-z0-9_-]+[.]parquet$'),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            schema_fingerprint text NOT NULL CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$'),
            byte_size bigint NOT NULL CHECK (byte_size>0),
            row_count bigint NOT NULL CHECK (row_count>0),
            min_period date NOT NULL,
            max_period date NOT NULL CHECK (max_period>=min_period),
            UNIQUE(version_id,storage_path)
        );
        CREATE TABLE validation_results (
            id uuid PRIMARY KEY,
            version_id uuid NOT NULL REFERENCES data_versions(id),
            step_id uuid NOT NULL REFERENCES refresh_steps(id),
            manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
            checkset_version text NOT NULL,
            check_code text NOT NULL CHECK (check_code ~ '^[VD][0-9]{2}$'),
            check_revision integer NOT NULL CHECK (check_revision>0),
            dataset_key text NOT NULL CHECK (dataset_key IN ('national','facility','generator','all')),
            required boolean NOT NULL,
            severity text NOT NULL CHECK (severity IN ('required','info','warning')),
            status text NOT NULL CHECK (status IN ('pass','fail','error')),
            checked_count bigint NOT NULL CHECK (checked_count>=0),
            failed_count bigint NOT NULL CHECK (failed_count BETWEEN 0 AND checked_count),
            details jsonb NOT NULL,
            details_path text NOT NULL,
            details_sha256 text NOT NULL CHECK (details_sha256 ~ '^[0-9a-f]{64}$'),
            checked_at timestamptz NOT NULL,
            CHECK (required=(severity='required')),
            CHECK (status<>'pass' OR failed_count=0),
            CHECK (status<>'fail' OR failed_count>0),
            CHECK (NOT required OR status<>'pass' OR checked_count>0),
            UNIQUE(version_id,step_id,check_code,dataset_key)
        );
        CREATE INDEX validation_step_results ON validation_results(step_id);

        CREATE FUNCTION refresh_check_result_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM data_versions v JOIN refresh_steps s ON s.run_id=v.run_id
                WHERE v.id=NEW.version_id AND s.id=NEW.step_id AND s.stage='validate'
                  AND v.manifest_sha256=NEW.manifest_sha256
                  AND v.validation_checkset=NEW.checkset_version
                  AND s.validation_attempt_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Invalid validation ownership' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_result_owner BEFORE INSERT OR UPDATE ON validation_results
            FOR EACH ROW EXECUTE FUNCTION refresh_check_result_owner();

        CREATE FUNCTION refresh_check_selected_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE candidate record;
        BEGIN
            FOR candidate IN SELECT v.* FROM data_versions v
                WHERE v.preparation_receipt_sha256 IS NOT NULL AND
                    ((TG_TABLE_NAME='data_versions' AND v.id=NEW.id)
                     OR (TG_TABLE_NAME='refresh_steps' AND v.validation_step_id=NEW.id))
            LOOP
                IF NOT EXISTS (
                    SELECT 1 FROM refresh_steps s WHERE s.id=candidate.validation_step_id
                      AND s.run_id=candidate.run_id AND s.stage='validate' AND s.status='succeeded'
                      AND s.finished_at IS NOT NULL
                      AND s.validation_attempt_id=candidate.validation_attempt_id
                      AND s.validation_sha256 IS NOT NULL AND s.diagnostics_sha256 IS NOT NULL
                ) THEN
                    RAISE EXCEPTION 'Invalid selected validation attempt' USING ERRCODE='23514';
                END IF;
            END LOOP;
            RETURN NULL;
        END $$;
        CREATE CONSTRAINT TRIGGER refresh_selected_attempt AFTER INSERT OR UPDATE ON data_versions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION refresh_check_selected_attempt();
        CREATE CONSTRAINT TRIGGER refresh_selected_step AFTER UPDATE ON refresh_steps
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION refresh_check_selected_attempt();

        CREATE FUNCTION refresh_freeze_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME='data_versions' THEN
                IF OLD.preparation_receipt_sha256 IS NOT NULL AND
                    (to_jsonb(NEW) - ARRAY['revision','disposition','discarded_at','discarded_by'])
                    IS DISTINCT FROM
                    (to_jsonb(OLD) - ARRAY['revision','disposition','discarded_at','discarded_by']) THEN
                    RAISE EXCEPTION 'Frozen candidate evidence' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='refresh_steps' THEN
                IF EXISTS (SELECT 1 FROM data_versions WHERE validation_step_id=OLD.id
                           AND preparation_receipt_sha256 IS NOT NULL) AND NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'Frozen validation step' USING ERRCODE='23514';
                END IF;
            ELSIF EXISTS (SELECT 1 FROM data_versions WHERE id=CASE WHEN TG_OP='INSERT'
                          THEN NEW.version_id ELSE OLD.version_id END
                          AND preparation_receipt_sha256 IS NOT NULL) THEN
                RAISE EXCEPTION 'Frozen candidate evidence' USING ERRCODE='23514';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER refresh_frozen_version BEFORE UPDATE ON data_versions
            FOR EACH ROW EXECUTE FUNCTION refresh_freeze_evidence();
        CREATE TRIGGER refresh_frozen_step BEFORE UPDATE ON refresh_steps
            FOR EACH ROW EXECUTE FUNCTION refresh_freeze_evidence();
        CREATE TRIGGER refresh_frozen_artifact BEFORE INSERT OR UPDATE OR DELETE ON dataset_artifacts
            FOR EACH ROW EXECUTE FUNCTION refresh_freeze_evidence();
        CREATE TRIGGER refresh_frozen_result BEFORE INSERT OR UPDATE OR DELETE ON validation_results
            FOR EACH ROW EXECUTE FUNCTION refresh_freeze_evidence();
    """)


def downgrade():
    """Remove only this revision, for explicitly disposable databases."""
    op.execute("""
        DROP TRIGGER refresh_frozen_version ON data_versions;
        DROP TRIGGER refresh_selected_attempt ON data_versions;
        DROP TRIGGER refresh_selected_step ON refresh_steps;
        DROP TRIGGER refresh_frozen_step ON refresh_steps;
        DROP TABLE validation_results,dataset_artifacts;
        DROP FUNCTION refresh_check_result_owner(),refresh_check_selected_attempt(),refresh_freeze_evidence();
        ALTER TABLE data_versions DROP CONSTRAINT refresh_storage_proof,
            DROP COLUMN preparation_receipt_sha256,DROP COLUMN storage_verified_at;
        ALTER TABLE refresh_steps DROP CONSTRAINT validation_step_identity,
            DROP COLUMN validation_attempt_id,DROP COLUMN validation_sha256,DROP COLUMN diagnostics_sha256;
    """)
