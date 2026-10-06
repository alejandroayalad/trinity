"""Check the registration time budget without PostgreSQL or S3."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from trinity.refresh.registration import REGISTRATION_SECONDS
from trinity.workers.refresh import register_receipt


def run_with(seconds_left):
    """Build the run fields that register_receipt reads."""
    return {'id': uuid4(), 'execution_fence': 1,
            'execution_deadline_at': datetime.now(UTC) + timedelta(seconds=seconds_left),
            'worker_execution_ref': {'version_id': str(uuid4()),
                                     'validation_step_id': str(uuid4()),
                                     'receipt_sha256': '0' * 64}}


class RegistrationBudgetTests(unittest.TestCase):
    def test_budget_is_150_seconds(self):
        # A live run read 49 objects back in 14.2 seconds at best.
        # The earlier 30-second budget failed after a successful S3 save.
        self.assertEqual(REGISTRATION_SECONDS, 150)

    def test_worker_requests_the_full_budget_when_time_remains(self):
        with patch('trinity.workers.refresh.CandidateRegistration') as registration:
            register_receipt(object(), run_with(1000), Path('root'), lambda: 'storage')
        self.assertEqual(registration.return_value.register.call_args.kwargs['timeout_seconds'], 150)

    def test_worker_never_exceeds_the_remaining_execution_budget(self):
        with patch('trinity.workers.refresh.CandidateRegistration') as registration:
            register_receipt(object(), run_with(40), Path('root'), lambda: 'storage')
        self.assertLessEqual(registration.return_value.register.call_args.kwargs['timeout_seconds'], 40)


if __name__ == '__main__':
    unittest.main()
