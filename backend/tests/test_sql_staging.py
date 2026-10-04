"""Verify pinned synthetic manifests and actual Parquet bytes without S3 access."""
from dataclasses import replace
from datetime import date, datetime, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

from botocore.exceptions import ClientError
from trinity.auth.schemas import Publication
from trinity.contracts.datasets import DATASETS
from trinity.contracts.manifest import FileEntry, Manifest, sha256, schema_fingerprint
from trinity.publication.repository import PinnedPublication
from trinity.queries.runtime.sql_policy import validate_query
from trinity.queries.service import QueryDeadline
from trinity.queries.staging import PublishedReader, stage_query
from trinity.errors import Problem
from sql_fixture import write_table


def bundle(root):
    version, entries, objects = str(uuid4()), [], {}
    for dataset in DATASETS:
        for part in range(2 if dataset == 'national' else 1):
            path = write_table(root / (dataset + str(part)), dataset)
            data = path.read_bytes(); key = f'data/{dataset}-{part}.parquet'
            entries.append(FileEntry(dataset,key,sha256(data),schema_fingerprint(dataset,DATASETS[dataset].schema),
                                     len(data),3,date(2025,1,1),date(2025,1,3)))
            objects[key] = data
    manifest = Manifest(version,date(2025,1,1),date(2025,1,3),'a'*64,tuple(entries))
    objects['manifest.json'] = manifest.to_bytes()
    public = Publication(publication_event_id=uuid4(),version_id=__import__('uuid').UUID(version),
            published_at=datetime.now(timezone.utc),coverage_start=date(2025,1,1),
            coverage_end=date(2025,1,3),latest_observation_date=date(2025,1,3))
    return PinnedPublication(public,manifest.digest,'trinity-data-v1'), objects


class Client:
    def __init__(self, objects): self.objects, self.calls, self.bodies, self.failures = objects, [], [], []
    def get_object(self, *, Bucket, Key):
        self.calls.append(Key)
        if self.failures: raise self.failures.pop(0)
        key = Key.split('/',2)[2]
        data = self.objects[key]
        body = io.BytesIO(data); self.bodies.append(body)
        return {'Body': body, 'ContentLength': len(data)}


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pinned, self.objects = bundle(self.root / 'source')
        self.stage = self.root / 'stage'; self.stage.mkdir()
        self.client = Client(self.objects); self.waits = []
        self.reader = PublishedReader(self.client,SimpleNamespace(bucket='synthetic',prefix='versions'),sleep=self.waits.append)
        self.query = validate_query('SELECT outage FROM national_outages')

    def run_stage(self, pinned=None):
        return stage_query(self.stage,uuid4(),pinned or self.pinned,self.query,self.reader,QueryDeadline(30))

    def test_all_selected_files_only_and_sealed_request(self):
        result = self.run_stage()
        self.assertEqual(len(list((result.directory / 'data').glob('*.parquet'))),2)
        self.assertEqual(json.loads((result.directory / 'request.json').read_bytes())['operation_digest'],self.query.digest)
        self.assertEqual(len(self.client.calls),3)
        self.assertFalse(any('facility' in key or 'generator' in key for key in self.client.calls))
        self.assertTrue(all(body.closed for body in self.client.bodies))
        result.cleanup(); self.assertFalse(result.directory.exists())

    def test_digest_or_second_file_failure_removes_partial_stage(self):
        for key in ('manifest.json','data/national-1.parquet'):
            with self.subTest(key=key):
                original = self.objects[key]; self.objects[key] = original + b'changed'
                with self.assertRaises(Problem): self.run_stage()
                self.assertEqual(list(self.stage.iterdir()),[])
                self.objects[key] = original

    def test_wrong_publication_coverage_fails_before_data_reads(self):
        public = self.pinned.publication.model_copy(update={'coverage_end':date(2025,1,4)})
        with self.assertRaises(Problem): self.run_stage(replace(self.pinned,publication=public))
        self.assertEqual(len(self.client.calls),1)

    def test_temporary_retries_and_denial_has_no_retry(self):
        temporary = ClientError({'Error':{'Code':'SlowDown'},'ResponseMetadata':{'HTTPStatusCode':503}},'GetObject')
        self.client.failures = [temporary,temporary]
        self.run_stage().cleanup(); self.assertEqual(self.waits,[1,3])
        self.waits.clear()
        self.client.failures = [ClientError({'Error':{'Code':'AccessDenied'}},'GetObject')]
        with self.assertRaises(Problem): self.run_stage()
        self.assertEqual(self.waits,[])

    def test_symlink_root_and_existing_request_are_not_replaced(self):
        linked = self.root / 'linked'; linked.symlink_to(self.stage,target_is_directory=True)
        with self.assertRaises(Problem): stage_query(linked,uuid4(),self.pinned,self.query,self.reader,QueryDeadline(30))
        request = uuid4(); existing = self.stage / str(request); existing.mkdir()
        marker = existing / 'keep'; marker.write_text('preserve')
        with self.assertRaises(Problem): stage_query(self.stage,request,self.pinned,self.query,self.reader,QueryDeadline(30))
        self.assertEqual(marker.read_text(),'preserve')

    def test_expired_deadline_does_not_read(self):
        deadline = QueryDeadline(-1)
        with self.assertRaises(Problem): stage_query(self.stage,uuid4(),self.pinned,self.query,self.reader,deadline)
        self.assertEqual(self.client.calls,[])
