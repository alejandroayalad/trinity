"""Verify synthetic frozen bundles and pinning failures without database or S3."""
from dataclasses import replace
from datetime import datetime, timezone
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from trinity.connector.validate import (
    CheckResult, REQUIRED_CHECKS, DIAGNOSTIC_CHECKS, MESSAGES, diagnostic_identity,
)
from trinity.contracts.manifest import canonical_json, sha256
from trinity.errors import Problem
from trinity.publication.diagnostics import read_preview_diagnostics
from trinity.publication.repository import PreviewPublication, read_preview_publication
from trinity.queries.service import QueryDeadline
from trinity.queries.staging import PublishedReader
from test_preview_unit import publication
from test_sql_staging import Client


def frozen_fixture():
    public = publication()
    attempt = str(uuid4())
    binding = dict(version_id=str(public.version_id), attempt_id=attempt, manifest_sha256='a'*64,
                   checkset_version='trinity-data-v1', contract_version=1,
                   requested_start=public.coverage_start.isoformat(), requested_end=public.coverage_end.isoformat())
    objects = {}
    def results(pairs, required):
        checks = []
        for code, scope in pairs:
            observed = not required and (code, scope) in {('D02','national'), ('D01','facility'), ('D09','facility')}
            details = canonical_json({'canary': 'PRIVATE_DETAIL', 'not_applicable': 0})
            path = f'evidence/{attempt}/{code}-{scope}.json'
            objects[path] = details
            checks.append(CheckResult(binding['version_id'], attempt, binding['manifest_sha256'],
                        'trinity-data-v1', code, 1, scope, required,
                        'required' if required else 'info' if code in ('D07','D08','D09') else 'warning',
                        'fail' if observed else 'pass', 3, 1 if observed else 0, details, path,
                        '2026-10-03T00:00:00Z'))
        return checks
    required = results(REQUIRED_CHECKS, True)
    diagnostics = results(DIAGNOSTIC_CHECKS, False)
    digest, count, summaries = diagnostic_identity(diagnostics)
    warning = dict(warning_digest=digest, warning_count=count, approval_required=count > 0)
    objects[f'evidence/{attempt}/validation.json'] = canonical_json(binding | {
        'status':'passed','expected_checks': REQUIRED_CHECKS,'results':[r.to_dict() for r in required], 'error_code':None})
    objects[f'evidence/{attempt}/diagnostics.json'] = canonical_json(binding | warning | {
        'registry':'warnings-v1','frozen':True,'summaries':summaries,'evaluations':[r.to_dict() for r in diagnostics]})
    artifacts = [dict(storage_path=k, sha256=sha256(v), byte_size=len(v)) for k,v in objects.items()]
    artifacts.append(dict(storage_path='manifest.json', sha256='a'*64, byte_size=1))
    bundle = binding | warning | dict(bundle_format=1, published=False, artifacts=artifacts)
    objects['bundle.json'] = canonical_json(bundle)
    pinned = PreviewPublication(public,'a'*64,'trinity-data-v1',sha256(objects['bundle.json']),attempt,
                                'trinity-data-v1',digest,count,count > 0)
    return pinned, objects


def changed_summary(pinned, objects, name, mutate):
    """Rehash altered summaries so tests reach schema checks beyond byte integrity."""
    import json
    path = f'evidence/{pinned.validation_attempt_id}/{name}.json'
    body = json.loads(objects[path])
    mutate(body)
    objects[path] = canonical_json(body)
    bundle = json.loads(objects['bundle.json'])
    for item in bundle['artifacts']:
        if item['storage_path'] == path:
            item.update(sha256=sha256(objects[path]), byte_size=len(objects[path]))
    objects['bundle.json'] = canonical_json(bundle)
    return replace(pinned, evidence_bundle_sha256=sha256(objects['bundle.json']))


class ProvenanceTests(unittest.TestCase):
    def read(self, pinned, objects, dataset='national'):
        client = Client(objects)
        reader = PublishedReader(client, SimpleNamespace(bucket='synthetic',prefix='versions'))
        result = read_preview_diagnostics(pinned, dataset, reader, QueryDeadline(30))
        self.assertEqual(len(client.calls), 3)
        self.assertFalse(any('parquet' in path for path in client.calls))
        return result

    def test_complete_evidence_projects_only_requested_scope_and_no_details(self):
        pinned, objects = frozen_fixture()
        national = self.read(pinned, objects)
        self.assertEqual([item.code for item in national], ['D02'])
        self.assertEqual(national[0].affected_count, '1')
        self.assertNotIn('PRIVATE_DETAIL', str(national))
        self.assertEqual([item.code for item in self.read(pinned, objects, 'facility')], ['D01'])
        self.assertEqual(self.read(pinned, objects, 'generator'), [])

    def test_existing_producer_bundle_is_read_without_rewriting_its_evidence(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from uuid import UUID
        from test_parquet import START, END
        from test_validate import reconciled, records_for
        from test_s3 import MemoryS3
        from trinity.adapters.s3 import S3Storage
        from trinity.config import S3Settings
        from trinity.connector.parquet import freeze_files
        from trinity.connector.validate import validate_candidate
        from trinity.connector.pipeline import store_candidate
        with TemporaryDirectory() as directory:
            frozen = freeze_files(output_root=Path(directory).resolve(), start=START, end=END,
                                  retrieval=records_for(reconciled()))
            report = validate_candidate(frozen.root, frozen.manifest_sha256)
            storage = MemoryS3()
            receipt = store_candidate(report, S3Storage(S3Settings('synthetic-bucket','versions','us-east-1'),
                                                        client=storage))
            objects = {key.split('/',2)[2]:value for key,value in storage.objects.items()}
            before = dict(objects)
            public = publication(version_id=UUID(report.manifest.version_id), coverage_start=START,
                                 coverage_end=END,latest_observation_date=END)
            pinned = PreviewPublication(public,report.manifest.digest,'trinity-data-v1',receipt.bundle_sha256,
                                        report.attempt_id,'trinity-data-v1',report.warning_digest,
                                        report.warning_count,report.approval_required)
            self.assertEqual(self.read(pinned,objects),[])
            self.assertEqual(objects,before)
            self.assertFalse(receipt.published)

    def test_missing_or_tampered_member_never_means_no_diagnostics(self):
        for name in ('bundle.json', 'validation.json', 'diagnostics.json'):
            pinned, objects = frozen_fixture()
            key = name if name == 'bundle.json' else f'evidence/{pinned.validation_attempt_id}/{name}'
            objects[key] += b' '
            with self.subTest(name=name), self.assertRaises(Problem):
                self.read(pinned, objects)
        pinned, objects = frozen_fixture()
        del objects[f'evidence/{pinned.validation_attempt_id}/diagnostics.json']
        with self.assertRaises(Problem):
            self.read(pinned, objects)

    def test_complete_hashes_do_not_excuse_partial_or_mixed_evaluations(self):
        cases = [('diagnostics',lambda b:b['evaluations'].pop()),
                 ('diagnostics',lambda b:b.update(frozen=False)),
                 ('diagnostics',lambda b:b['evaluations'][0].update(status='error')),
                 ('diagnostics',lambda b:b['evaluations'][0].update(attempt_id=str(uuid4()))),
                 ('diagnostics',lambda b:b.update(summaries=[])),
                 ('diagnostics',lambda b:b.update(registry='unknown')),
                 ('validation',lambda b:b['results'][0].update(status='fail', failed_count=1)),
                 ('validation',lambda b:b['results'].append(b['results'][0])),
                 ('validation',lambda b:b.update(expected_checks=[]))]
        for name, mutate in cases:
            pinned, objects = frozen_fixture()
            pinned = changed_summary(pinned, objects, name, mutate)
            with self.subTest(name=name, mutate=mutate), self.assertRaises(Problem):
                self.read(pinned, objects)

    def test_wrong_pinned_identity_and_expired_budget_fail(self):
        pinned, objects = frozen_fixture()
        for changed in (replace(pinned,validation_attempt_id=str(uuid4())),
                        replace(pinned,review_warning_digest='b'*64), replace(pinned,review_warning_count=0)):
            with self.assertRaises(Problem):
                self.read(changed, objects)
        reader = Mock()
        reader.read_into.side_effect = Problem(504,'query_timeout')
        with self.assertRaises(Problem) as error:
            read_preview_diagnostics(pinned, 'national', reader, QueryDeadline(-1))
        self.assertEqual(error.exception.code,'query_timeout')

    def test_pin_requires_successful_same_run_and_exact_approval(self):
        pinned, _ = frozen_fixture()
        step, approval = uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        row = dict(evidence_bundle_sha256=pinned.evidence_bundle_sha256,
                   validation_attempt_id=pinned.validation_attempt_id, validation_checkset=pinned.validation_checkset,
                   review_warning_digest=pinned.review_warning_digest,review_warning_count=pinned.review_warning_count,
                   approval_required=True, diagnostics_frozen_at=now,validated_at=now, validation_step_id=step,
                   same_run=True, stage='validate',step_status='succeeded',finished_at=now,
                   publication_mode='approval',approval_id=approval, approved_version=pinned.publication.version_id,
                   approved_manifest=pinned.manifest_sha256,approved_step=step,approved_digest=pinned.review_warning_digest)
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = row
        self.assertEqual(read_preview_publication(connection,pinned), pinned)
        for changes in ({'same_run':False}, {'stage':'extract'}, {'step_status':'failed'},
                        {'evidence_bundle_sha256':None}, {'validation_attempt_id':None},
                        {'diagnostics_frozen_at':None}, {'approved_step':uuid4()}, {'approved_digest':'b'*64},
                        {'approval_required':False}, {'validation_checkset':'other'}):
            connection.execute.return_value.fetchone.return_value = row | changes
            with self.subTest(changes=changes), self.assertRaises(Problem):
                read_preview_publication(connection,pinned)
