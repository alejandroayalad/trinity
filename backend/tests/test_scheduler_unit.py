"""Offline checks for scheduler logging, the poll loop and the worker role start.

These tests need no database. The role-start test runs the real worker
process with a database URL that cannot connect. It proves that the role
starts with only TRINITY_DATABASE_URL and that its log never shows the
URL's password.
"""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from uuid import UUID

from trinity.errors import Problem
from trinity.workers import scheduler
from trinity.workers.scheduler import Outcome, log_outcome

# A synthetic password. If any log line contains it, a secret leaked.
SENTINEL = "sentinel-password-7f3a"


class StopAfterOne:
    """Act as a scheduler service that fails once and then stops the loop."""

    def __init__(self, stop, error):
        self.stop, self.error = stop, error

    def once(self):
        self.stop.set()
        raise self.error


class SchedulerLogTests(unittest.TestCase):
    def run_loop(self, error):
        async def scenario():
            stop = asyncio.Event()
            await scheduler.run(StopAfterOne(stop, error), stop, interval=0.01)
        with self.assertLogs("trinity.scheduler", level="DEBUG") as captured:
            asyncio.run(scenario())
        return captured.output

    def test_exception_text_is_never_logged(self):
        # The exception message holds a URL with a password, as a driver
        # error could. Only the fixed reason code may reach the log.
        output = self.run_loop(RuntimeError(f"postgresql://user:{SENTINEL}@db/trinity"))
        self.assertEqual(output, ["WARNING:trinity.scheduler:scheduler outcome=error revision=- "
                                  "occurrence=- reason=unexpected run_id=-"])

    def test_problem_logs_only_its_code(self):
        output = self.run_loop(Problem(503, "dependency_unavailable"))
        self.assertEqual(output, ["WARNING:trinity.scheduler:scheduler outcome=error revision=- "
                                  "occurrence=- reason=dependency_unavailable run_id=-"])

    def test_outcome_lines_have_fixed_fields(self):
        instant = datetime(2026, 10, 6, 10, 15, tzinfo=timezone.utc)
        run_id = UUID("00000000-0000-4000-8000-000000000001")
        with self.assertLogs("trinity.scheduler", level="DEBUG") as captured:
            log_outcome(Outcome("idle"))
            log_outcome(Outcome("admitted", 4, instant, run_id=run_id))
            log_outcome(Outcome("blocked", 4, instant, reason="refresh_active"))
        self.assertEqual(captured.output, [
            "DEBUG:trinity.scheduler:scheduler outcome=idle revision=- occurrence=- reason=- run_id=-",
            f"INFO:trinity.scheduler:scheduler outcome=admitted revision=4 occurrence=2026-10-06T10:15:00Z "
            f"reason=- run_id={run_id}",
            "INFO:trinity.scheduler:scheduler outcome=blocked revision=4 occurrence=2026-10-06T10:15:00Z "
            "reason=refresh_active run_id=-",
        ])


class SchedulerRoleStartTests(unittest.TestCase):
    def test_role_starts_with_only_database_url_and_hides_it(self):
        # The socket directory does not exist, so every connection fails
        # after the pool timeout. The role must keep running, log a fixed
        # error line and stop cleanly on SIGTERM.
        backend = Path(__file__).resolve().parents[1]
        url = f"postgresql://scheduler_check:{SENTINEL}@/trinity_missing?host=/nonexistent-trinity-socket"
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(backend / "src"), "TRINITY_DATABASE_URL": url}
        process = subprocess.Popen([sys.executable, "-m", "trinity.workers", "scheduler"], cwd=backend, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # The pool waits up to 5 seconds for a connection. Wait longer so
            # the first evaluation has finished and logged its outcome.
            time.sleep(8)
            self.assertIsNone(process.poll(), "the role stopped instead of retrying")
        finally:
            process.send_signal(signal.SIGTERM)
            output, errors = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, errors)
        self.assertIn("scheduler outcome=error revision=- occurrence=- reason=dependency_unavailable run_id=-", errors)
        self.assertNotIn(SENTINEL, output + errors)
        self.assertNotIn("nonexistent-trinity-socket", output + errors)


if __name__ == "__main__":
    unittest.main()
