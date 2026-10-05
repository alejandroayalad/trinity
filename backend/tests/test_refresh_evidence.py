"""Reject mixed or incomplete candidate receipts before any database mutation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from refresh_fixture import stored_result
from trinity.errors import Problem
from trinity.refresh.evidence import load_candidate


class RefreshEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.report,self.receipt,self.objects,self.storage,self.digest = stored_result(Path(self.temp.name))

    def test_reconstructs_original_report_and_preview_bundle_identity(self):
        evidence = load_candidate(self.report.root,self.digest,self.storage)
        self.assertEqual(evidence.report,self.report)
        self.assertEqual(evidence.receipt,self.receipt)

    def test_rejects_child_only_completion(self):
        (self.report.root/'evidence/preparation/result.json').unlink()
        with self.assertRaises(Problem):
            load_candidate(self.report.root,self.digest,self.storage)

    def test_retained_digest_cannot_be_replaced_by_current_file_hash(self):
        with self.assertRaises(Problem):
            load_candidate(self.report.root,'a'*64,self.storage)

    def test_changed_detail_or_remote_object_is_not_repaired(self):
        path = self.report.results[0].details_path
        original = (self.report.root/path).read_bytes()
        (self.report.root/path).write_bytes(b'{}')
        with self.assertRaises(Problem):
            load_candidate(self.report.root,self.digest,self.storage)
        (self.report.root/path).write_bytes(original)
        key = f'versions/{self.receipt.version_id}/data/national.parquet'
        self.storage.client.objects[key] = b'changed'
        with self.assertRaises(Problem):
            load_candidate(self.report.root,self.digest,self.storage)
        self.assertEqual(self.storage.client.objects[key],b'changed')

    def test_contradictory_parent_failure_blocks_completion(self):
        (self.report.root/'evidence/preparation/failure.json').write_bytes(b'{}')
        with self.assertRaises(Problem):
            load_candidate(self.report.root,self.digest,self.storage)
