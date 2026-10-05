"""Exercise real error wrappers and reject queue authority before protected reads."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from botocore.exceptions import EndpointConnectionError
from refresh_fixture import stored_result
from test_s3 import sdk_error
from trinity.refresh.evidence import load_candidate, EvidenceError
from trinity.adapters.queue import publication_payload

class PublicationEvidenceTests(unittest.TestCase):
    def test_actual_storage_wrapper_classifies_retry_without_raw_error_text(self):
        with TemporaryDirectory() as root:
            report,receipt,objects,storage,digest=stored_result(Path(root),warnings=False)
            storage.sleep=lambda _:None
            for error,cause,attempts in (
                (EndpointConnectionError(endpoint_url='private-canary'),'storage_temporary',3),
                (sdk_error('NoSuchKey',404),'evidence_missing',1),
                (sdk_error('AccessDenied',403),'storage_denied',1),
                (RuntimeError('private-canary'),'unknown_failure',1)):
                calls=[]
                def fail(**kwargs):
                    calls.append(1);raise error
                storage.client.get_object=fail
                with self.assertRaises(EvidenceError) as failure:
                    load_candidate(report.root,digest,storage)
                self.assertEqual(failure.exception.code,'dependency_unavailable')
                self.assertEqual(failure.exception.cause,cause)
                self.assertEqual(len(calls),attempts)
                self.assertNotIn('private-canary',str(failure.exception))

    def test_missing_altered_and_mixed_evidence_fail_closed(self):
        with TemporaryDirectory() as root:
            report,receipt,objects,storage,digest=stored_result(Path(root),warnings=False)
            for bad_digest in ('a'*64,None,''):
                with self.assertRaises(EvidenceError) as error:load_candidate(report.root,bad_digest,storage)
                self.assertNotEqual(error.exception.cause,'storage_temporary')
            (report.root/'evidence/preparation/result.json').unlink()
            with self.assertRaises(EvidenceError) as error:load_candidate(report.root,digest,storage)
            self.assertNotEqual(error.exception.cause,'storage_temporary')

    def test_queue_payload_rejects_path_authority_and_boolean_generations(self):
        from uuid import uuid4
        value=dict(schema_version=1,run_id=str(uuid4()),version_id=str(uuid4()),
                   job_kind='publish_version',publication_generation=0,dispatch_generation=0)
        self.assertEqual(publication_payload(value),value)
        for change in ({'root':'private'},{'publication_generation':True},{'dispatch_generation':-1},
                       {'job_kind':'refresh_pipeline'},{'version_id':'not-a-uuid'}):
            with self.assertRaises((ValueError,TypeError)):publication_payload(value|change)
