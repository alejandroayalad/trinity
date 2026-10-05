"""Verify new writer state against the existing Preview reader in real PostgreSQL.

All SQL runs in the runner's disposable cluster. Storage contains synthetic
bytes from the real preparation library. Publication below is an explicit test
effect: it never seeds replacement candidate fields to make Preview accept them.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from alembic import command
from alembic.script import ScriptDirectory
import psycopg
from psycopg.types.json import Jsonb

from postgres_fixture import PostgresFixture, DSN
from preview_fixture import publish_fixture
from preview_runtime_fixture import ObjectClient
from refresh_fixture import stored_result
from test_preview_unit import codec
from trinity.adapters.postgres import Deadline
from trinity.errors import Problem
from trinity.publication.diagnostics import read_preview_diagnostics
from trinity.publication.repository import read_pinned_publication, read_preview_publication
from trinity.queries.service import PreviewService, QueryDeadline
from trinity.queries.staging import PublishedReader
from trinity.refresh.evidence import load_candidate
from trinity.refresh.registration import CandidateRegistration, persist_candidate


@unittest.skipUnless(DSN, 'Use run_local_sql_checks.py --refresh for disposable PostgreSQL')
class RefreshPostgresTests(PostgresFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.report,self.receipt,self.objects,self.storage,self.digest = stored_result(Path(self.temp.name))
        self.run,self.step = uuid4(),uuid4()
        self.version = UUID(self.report.manifest.version_id)
        self.writer = CandidateRegistration(self.database)

    def reserve(self):
        """Seed only the worker-owned preconditions; the writer creates evidence."""
        self.setup_done()
        start,end = self.report.manifest.requested_start,self.report.manifest.requested_end
        policy = {'workflow_policy':'warnings-v1','diagnostic_registry':'warnings-v1',
                  'contract_version':'trinity-data-v1','validation_checkset':'trinity-data-v1',
                  'requested_start':start.isoformat(),'settings_revision':1,'end_strategy':'fixed',
                  'explicit_end':end.isoformat()}
        self.sql("""INSERT INTO refresh_runs(id,trigger_kind,requested_by,request_key,requested_at,
            started_at,status,settings_revision,policy_snapshot,requested_start,requested_end,
            window_frozen_at,execution_fence,lease_until) VALUES(%s,'manual','test_admin',%s,now(),
            now(),'running',1,%s,%s,%s,now(),1,now()+interval '10 minutes')""",
            (self.run,uuid4(),Jsonb(policy),start,end))
        self.sql('UPDATE refresh_control SET holder_run_id=%s WHERE id=1',(self.run,))
        self.sql("""INSERT INTO refresh_steps(id,run_id,step_seq,stage,work_key,attempt,status,
            execution_fence,started_at,progress_unit,validation_attempt_id)
            VALUES(%s,%s,1,'validate','candidate',1,'running',1,now(),'checks',%s)""",
            (self.step,self.run,UUID(self.report.attempt_id)))
        self.sql("""INSERT INTO data_versions(id,run_id,status,disposition,created_at,
            manifest_frozen_at,manifest_sha256,coverage_start,coverage_end,latest_observation_date,
            contract_version,validation_checkset) VALUES(%s,%s,'validating','active',now(),now(),
            %s,%s,%s,%s,'trinity-data-v1','trinity-data-v1')""",
            (self.version,self.run,self.report.manifest.digest,start,end,end))

    def register(self, **changes):
        args = dict(run_id=self.run,version_id=self.version,step_id=self.step,fence=1,
                    root=self.report.root,receipt_sha256=self.digest,storage=self.storage)
        return self.writer.register(**(args | changes))

    def publish_registered(self):
        """Apply only the later publication effect to already registered evidence."""
        event,approval = uuid4(),uuid4()
        with self.database.transaction(Deadline()) as connection:
            if self.report.approval_required:
                connection.execute("""INSERT INTO approvals(id,version_id,approved_by,approved_at,
                    manifest_sha256,validation_step_id,review_warning_digest)
                    VALUES(%s,%s,'test_admin',now(),%s,%s,%s)""",
                    (approval,self.version,self.report.manifest.digest,self.step,self.report.warning_digest))
            connection.execute("""INSERT INTO publication_events(id,version_id,published_at,
                publication_mode,approval_id,actor_id,idempotency_key)
                VALUES(%s,%s,now(),%s,%s,%s,%s)""",
                (event,self.version,'approval' if self.report.approval_required else 'automatic',
                 approval if self.report.approval_required else None,
                 'test_admin' if self.report.approval_required else None,self.version))
            connection.execute('UPDATE active_publication SET publication_event_id=%s WHERE id=1',(event,))
            connection.execute("UPDATE refresh_runs SET status='succeeded',finished_at=now() WHERE id=%s",(self.run,))
            connection.execute('UPDATE refresh_control SET holder_run_id=NULL WHERE id=1')
        return event

    def test_writer_review_handoff_is_accepted_by_actual_preview_service(self):
        self.reserve()
        self.assertEqual(self.register(),'awaiting_approval')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],39)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM dataset_artifacts')[0]['n'],3)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM job_outbox')[0]['n'],0)
        self.assertIsNone(self.sql('SELECT lease_until FROM refresh_runs')[0]['lease_until'])
        self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])
        self.publish_registered()
        client = ObjectClient()
        client.add(self.version,self.objects)
        reader = PublishedReader(client,SimpleNamespace(bucket='synthetic',prefix='versions'))
        execution = Mock(deployment_id=uuid4(),daemon_id='refresh-compatibility')
        # Execute the real Preview service through metadata pinning and admission.
        # This controlled executor checks production provenance; container row
        # execution remains the separate, already existing runtime suite.
        execution.execute.side_effect = lambda prepared: (
            prepared.pinned,
            read_preview_diagnostics(prepared.pinned,'national',reader,prepared.deadline))
        previews = PreviewService(self.database,lambda:execution,codec_factory=codec)
        token = self.login('analyst')['Authorization'][7:]
        pinned,diagnostics = previews.execute(token,'national_outages',[])
        self.assertEqual(pinned.evidence_bundle_sha256,self.receipt.bundle_sha256)
        self.assertEqual(pinned.validation_attempt_id,self.report.attempt_id)
        self.assertTrue(any(note.code=='D02' for note in diagnostics))

    def test_warning_free_handoff_and_exact_replay_enqueue_once(self):
        self.report,self.receipt,self.objects,self.storage,self.digest = stored_result(Path(self.temp.name),warnings=False)
        self.version = UUID(self.report.manifest.version_id)
        self.reserve()
        self.assertEqual(self.register(),'publishing')
        self.assertEqual(self.register(),'publishing')
        rows = self.sql('SELECT * FROM job_outbox')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['payload']['version_id'],str(self.version))
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],39)
        self.assertIsNone(self.sql('SELECT publication_event_id FROM active_publication')[0]['publication_event_id'])

    def test_wrong_attempt_and_stale_fence_leave_candidate_unvalidated(self):
        self.reserve()
        with self.assertRaises(Problem): self.register(fence=2)
        self.sql('UPDATE refresh_steps SET validation_attempt_id=%s WHERE id=%s',(uuid4(),self.step))
        with self.assertRaises(Problem): self.register()
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'validating')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM dataset_artifacts')[0]['n'],0)

    def test_registration_transaction_failure_rolls_back_all_evidence(self):
        self.reserve()
        evidence = load_candidate(self.report.root,self.digest,self.storage)
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with self.database.transaction(Deadline()) as connection:
                persist_candidate(connection,self.run,self.version,self.step,1,evidence)
                raise RuntimeError('injected')
        self.assertEqual(self.sql('SELECT count(*) AS n FROM validation_results')[0]['n'],0)
        self.assertEqual(self.sql('SELECT count(*) AS n FROM dataset_artifacts')[0]['n'],0)
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'validating')
        self.assertEqual(self.register(),'awaiting_approval')

    def test_expired_or_unclaimed_writer_is_denied_before_evidence_reads(self):
        self.reserve()
        with patch('trinity.refresh.registration.load_candidate') as read:
            self.sql("UPDATE refresh_runs SET lease_until=now()-interval '1 second'")
            with self.assertRaises(Problem): self.register()
            self.sql("UPDATE refresh_runs SET status='requested',lease_until=now()+interval '1 minute'")
            with self.assertRaises(Problem): self.register()
            read.assert_not_called()

    def test_outbox_rejects_partial_or_out_of_state_lease(self):
        self.reserve()
        self.sql("""INSERT INTO job_outbox(id,run_id,job_kind,deduplication_key,payload)
            VALUES(%s,%s,'refresh_pipeline',%s,'{}')""", (uuid4(),self.run,str(self.run)))
        for statement in (
            'UPDATE job_outbox SET lease_token=gen_random_uuid()',
            "UPDATE job_outbox SET status='dispatching',lease_until=now()",
            "UPDATE job_outbox SET status='delivered'",
        ):
            with self.assertRaises(psycopg.errors.CheckViolation): self.sql(statement)

    def test_committed_identity_and_selected_step_cannot_be_rebound(self):
        self.reserve();self.register()
        for statement,params in (
            ('UPDATE data_versions SET validation_attempt_id=%s',(uuid4(),)),
            ('UPDATE data_versions SET evidence_bundle_sha256=%s',('a'*64,)),
            ('UPDATE refresh_steps SET validation_attempt_id=%s',(uuid4(),)),
            ('DELETE FROM validation_results',()),
            ('UPDATE dataset_artifacts SET sha256=%s',('b'*64,)),
        ):
            with self.assertRaises(psycopg.errors.CheckViolation): self.sql(statement,params)

    def test_selected_attempt_constraint_rejects_wrong_step_at_commit(self):
        self.reserve()
        evidence = load_candidate(self.report.root,self.digest,self.storage)
        # Defer the identity check until the transaction contains all writes.
        # A wrongly selected attempt must fail even when SQL bypasses services.
        with self.assertRaises(Problem):
            with self.database.transaction(Deadline()) as connection:
                connection.execute('UPDATE refresh_steps SET validation_sha256=%s,diagnostics_sha256=%s',
                                   ('a'*64,'b'*64))
                connection.execute("""UPDATE data_versions SET status='validated',validated_at=now(),
                    validation_step_id=%s,validation_attempt_id=%s,evidence_bundle_sha256=%s,
                    preparation_receipt_sha256=%s,storage_verified_at=now(),diagnostics_frozen_at=now(),
                    approval_required=true,review_warning_count=1,review_warning_digest=%s""",
                    (self.step,uuid4(),self.receipt.bundle_sha256,self.digest,self.report.warning_digest))
        self.assertEqual(self.sql('SELECT status FROM data_versions')[0]['status'],'validating')

    def test_upgrade_from_preview_preserves_its_evidence_and_has_one_head(self):
        with patch.dict(os.environ,{'TRINITY_DATABASE_URL':DSN}):
            command.downgrade(self.migration,'0004_preview_evidence')
            try:
                event,version = publish_fixture(DSN,self.report,self.receipt)
                before = self.sql('SELECT * FROM data_versions WHERE id=%s',(version,))[0]
                command.upgrade(self.migration,'head')
            finally:
                command.upgrade(self.migration,'head')
        after = self.sql('SELECT * FROM data_versions WHERE id=%s',(version,))[0]
        self.assertEqual(before,{key:after[key] for key in before})
        self.assertIsNone(after['preparation_receipt_sha256'])
        self.assertEqual(ScriptDirectory.from_config(self.migration).get_heads(),['0007_refresh_registration'])
        with self.database.transaction(QueryDeadline(10),readonly=True) as connection:
            pinned = read_preview_publication(connection,read_pinned_publication(connection))
        self.assertEqual(pinned.evidence_bundle_sha256,self.receipt.bundle_sha256)
