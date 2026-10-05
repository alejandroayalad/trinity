"""Opt-in real PostgreSQL checks for the scheduler role.

Run through tests/run_local_refresh_checks.py (or run_local_sql_checks.py
--refresh). The runner creates a disposable cluster and sets
TRINITY_TEST_DATABASE_URL. Every test truncates the application tables, so
never point this variable at retained data.

Most tests pass a fixed test clock to SchedulerService. The occurrence T is
06:15 in America/New_York on 2026-10-06, which is 10:15:00Z. A test clock
instant such as T + 20 seconds stands for "the scheduler evaluates at
06:15:20". One test starts the real worker process with the PostgreSQL clock.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import multiprocessing
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import unittest
from uuid import uuid4

import psycopg

from postgres_fixture import DSN, PostgresFixture
from trinity.adapters.postgres import Database
from trinity.adapters.queue import RefreshQueue, job_id
from trinity.config import ApiSettings
from trinity.errors import Problem
from trinity.refresh.dispatch import DispatchService
from trinity.refresh.repository import POLICY
from trinity.settings.schedule import occurrence_key
from trinity.workers import outbox
from trinity.workers.scheduler import SchedulerService

T = datetime(2026, 10, 6, 10, 15, tzinfo=timezone.utc)
SECOND = timedelta(seconds=1)
REDIS_PORT = os.environ.get("TRINITY_TEST_REDIS_PORT")


def at(instant):
    """Return a test clock that always reports one instant."""
    return lambda _connection: instant


def scheduler_contender(dsn, instant, ready, start, result):
    """Evaluate once from a separate process with its own connection pool."""
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    ready.put(True)
    start.wait(10)
    try:
        outcome = SchedulerService(database, clock=at(datetime.fromisoformat(instant))).once()
        result.put(("scheduler", outcome.code, outcome.reason))
    except Problem as error:
        result.put(("scheduler", "error", error.code))
    finally:
        database.close()


def manual_contender(dsn, token, delay, ready, start, result):
    """Press Start from a separate process, like a second Admin browser.

    delay is the number of seconds to wait after the start signal. A delay
    lets a scheduler reach refresh_control first.
    """
    from trinity.refresh.service import RefreshService
    database = Database(ApiSettings(TRINITY_DATABASE_URL=dsn))
    database.open()
    ready.put(True)
    start.wait(10)
    time.sleep(delay)
    try:
        RefreshService(database).start(token, b"{}", [str(uuid4())])
        result.put(("manual", "accepted", None))
    except Problem as error:
        result.put(("manual", error.code, None))
    finally:
        database.close()


@unittest.skipUnless(DSN, "Use tests/run_local_refresh_checks.py")
class SchedulerPostgresTests(PostgresFixture, unittest.TestCase):
    def schedule(self, *, revision=4, daily_time="06:15", zone="America/New_York", enabled=True,
                 updated_at=T - timedelta(days=1)):
        """Store a set-up schedule whose last save is at updated_at."""
        self.sql("""UPDATE shared_settings SET setup_completed_at=%s, updated_at=%s, updated_by='test_admin',
            daily_time=%s, schedule_timezone=%s, schedule_enabled=%s, revision=%s""",
                 (updated_at, updated_at, daily_time, zone, enabled, revision))

    def once(self, instant):
        return SchedulerService(self.database, clock=at(instant)).once()

    def counts(self):
        return {table: self.sql(f"SELECT count(*) AS n FROM {table}")[0]["n"]
                for table in ("refresh_runs", "job_outbox", "api_commands")}

    def holder(self):
        return self.sql("SELECT holder_run_id FROM refresh_control")[0]["holder_run_id"]

    def release_slot(self):
        """Free the lifecycle slot without changing the run row.

        Later tests need "no blocker now". The scheduler only reads the
        slot holder, so clearing it is enough and avoids building a full
        finished-run fixture.
        """
        self.sql("UPDATE refresh_control SET holder_run_id=NULL")

    def test_due_occurrence_admits_one_run_like_manual_start(self):
        # Row 1: occurrence 06:15, evaluated at 06:15:20, no blocker.
        self.schedule()
        outcome = self.once(T + 20 * SECOND)
        self.assertEqual((outcome.code, outcome.revision, outcome.occurrence), ("admitted", 4, T))
        run = self.sql("SELECT * FROM refresh_runs")[0]
        self.assertEqual((run["id"], run["trigger_kind"], run["requested_by"], run["status"]),
                         (outcome.run_id, "scheduled", None, "requested"))
        self.assertEqual((run["request_key"], run["settings_revision"]), (occurrence_key(4, T), 4))
        self.assertEqual(run["policy_snapshot"], {"settings_revision": 4, **POLICY})
        self.assertEqual(self.holder(), run["id"])
        outbox = self.sql("SELECT * FROM job_outbox")
        self.assertEqual([(row["run_id"], row["job_kind"], row["payload"]["run_id"]) for row in outbox],
                         [(run["id"], "refresh_pipeline", str(run["id"]))])
        # No receipt: api_commands requires a human actor.
        self.assertEqual(self.counts(), {"refresh_runs": 1, "job_outbox": 1, "api_commands": 0})

    def test_same_identity_never_runs_twice(self):
        self.schedule()
        first = self.once(T + 20 * SECOND)
        # Row 2 and row 3: a second process, or a restart at 06:18, sees the
        # same identity and writes nothing. This holds even after the first
        # run left the slot, because the key check comes before the slot.
        self.assertEqual(self.once(T + 21 * SECOND).code, "duplicate")
        self.release_slot()
        again = SchedulerService(self.database, clock=at(T + 180 * SECOND)).once()
        self.assertEqual((again.code, again.run_id), ("duplicate", first.run_id))
        self.assertEqual(self.counts()["refresh_runs"], 1)

    def test_restart_inside_window_admits_and_after_window_misses(self):
        self.schedule()
        # Row 4: restart at 06:25 is outside the window; no run, no record.
        for instant in (T - SECOND, T + 300 * SECOND, T + 600 * SECOND):
            with self.subTest(instant=instant):
                self.assertEqual(self.once(instant).code, "idle")
        self.assertEqual(self.counts(), {"refresh_runs": 0, "job_outbox": 0, "api_commands": 0})
        # Row 3 without an earlier run: restart at 06:18 admits once.
        self.assertEqual(self.once(T + 180 * SECOND).code, "admitted")

    def test_down_for_a_day_starts_only_the_current_occurrence(self):
        self.schedule()
        next_day = T + timedelta(days=1)
        outcome = self.once(next_day + 20 * SECOND)
        self.assertEqual((outcome.code, outcome.occurrence), ("admitted", next_day))
        self.assertEqual(self.counts()["refresh_runs"], 1)

    def test_failed_run_blocks_and_is_not_retried_later(self):
        # Row 5: a failed run holds the slot at 06:15.
        run, _, _ = self.lifecycle("failed")
        self.schedule()
        before = self.counts()
        outcome = self.once(T + 20 * SECOND)
        self.assertEqual((outcome.code, outcome.reason), ("blocked", "failure_unresolved"))
        self.assertEqual((self.counts(), self.holder()), (before, run))
        # Resolving the failure at 09:00 does not start a late run.
        self.sql("DELETE FROM failure_warnings")
        self.release_slot()
        self.assertEqual(self.once(T + timedelta(hours=2, minutes=45)).code, "idle")
        self.assertEqual(self.counts(), before)

    def test_new_time_after_admitted_run_is_a_new_identity(self):
        # Row 6: the 06:15 run is admitted, then the Admin saves 06:20 at 06:16.
        self.schedule()
        first = self.once(T + 20 * SECOND)
        self.schedule(revision=5, daily_time="06:20", updated_at=T + 60 * SECOND)
        second_t = T + 5 * timedelta(minutes=1)
        blocked = self.once(second_t + 10 * SECOND)
        self.assertEqual((blocked.code, blocked.reason, blocked.occurrence), ("blocked", "refresh_active", second_t))
        # The same identity runs when no blocker exists at its evaluation.
        self.release_slot()
        admitted = self.once(second_t + 30 * SECOND)
        self.assertEqual(admitted.code, "admitted")
        keys = {row["request_key"] for row in self.sql("SELECT request_key FROM refresh_runs")}
        self.assertEqual(keys, {occurrence_key(4, T), occurrence_key(5, second_t)})
        self.assertNotEqual(admitted.run_id, first.run_id)

    def test_no_op_save_through_http_keeps_the_occurrence_due(self):
        # Row 7: a real PUT with identical values at 06:15:10 writes nothing.
        self.schedule()
        before = self.sql("SELECT * FROM shared_settings")[0]
        response = self.client.put("/api/v1/settings", headers={**self.login("admin"), "If-Match": '"settings-4"',
                                   "Content-Type": "application/json"},
                                   json={"schedule_enabled": True, "daily_time": "06:15", "timezone": "America/New_York"})
        self.assertEqual((response.status_code, response.headers["etag"]), (200, '"settings-4"'))
        self.assertEqual(self.sql("SELECT * FROM shared_settings")[0], before)
        self.assertEqual(self.once(T + 20 * SECOND).code, "admitted")

    def test_real_change_before_evaluation_skips_the_old_occurrence(self):
        # Row 8: only the timezone changes at 06:15:10. The old T is not after
        # the save, and 06:15 in Chicago is 11:15Z, so nothing is due.
        self.schedule()
        self.schedule(revision=5, zone="America/Chicago", updated_at=T + 10 * SECOND)
        self.assertEqual(self.once(T + 20 * SECOND).code, "idle")
        # The same rule applies when the values keep the same T: a disable and
        # enable at 06:15:10 is a new revision saved after T.
        self.schedule(revision=7, updated_at=T + 10 * SECOND)
        self.assertEqual(self.once(T + 20 * SECOND).code, "idle")
        self.assertEqual(self.counts()["refresh_runs"], 0)
        # The next occurrence uses the new timezone.
        chicago = datetime(2026, 10, 6, 11, 15, tzinfo=timezone.utc)
        self.schedule(revision=8, zone="America/Chicago", updated_at=T + 10 * SECOND)
        self.assertEqual(self.once(chicago + 20 * SECOND).occurrence, chicago)

    def test_manual_start_first_makes_the_occurrence_skip(self):
        # Row 9: the Admin presses Start at 06:15:05.
        self.schedule()
        response = self.client.post("/api/v1/refresh-runs", json={},
                                    headers={**self.login("admin"), "Idempotency-Key": str(uuid4())})
        self.assertEqual(response.status_code, 202, response.text)
        outcome = self.once(T + 20 * SECOND)
        self.assertEqual((outcome.code, outcome.reason), ("blocked", "refresh_active"))
        runs = self.sql("SELECT trigger_kind FROM refresh_runs")
        self.assertEqual(runs, [{"trigger_kind": "manual"}])

    def test_manual_key_equal_to_occurrence_key_is_skipped_as_duplicate(self):
        # The documented limit: an Admin can send the future occurrence key as
        # an Idempotency-Key. The key check then finds that manual run, so the
        # occurrence is skipped as `duplicate`; the unique constraint is not
        # reached and no error occurs.
        self.schedule()
        key = str(occurrence_key(4, T))
        response = self.client.post("/api/v1/refresh-runs", json={},
                                    headers={**self.login("admin"), "Idempotency-Key": key})
        self.assertEqual(response.status_code, 202, response.text)
        self.release_slot()
        self.assertEqual(self.once(T + 20 * SECOND).code, "duplicate")
        self.assertEqual(self.counts()["refresh_runs"], 1)

    def test_change_between_check_and_lock_is_rechecked(self):
        self.schedule()
        # The first clock call happens in the read-only check. Commit a save
        # from another connection at that point, as a concurrent PUT would.
        calls = []

        def save_during_check(_connection):
            if not calls:
                with psycopg.connect(DSN) as other:
                    other.execute("UPDATE shared_settings SET revision=5, updated_at=%s", (T + 10 * SECOND,))
            calls.append(True)
            return T + 20 * SECOND

        outcome = SchedulerService(self.database, clock=save_during_check).once()
        self.assertEqual((outcome.code, outcome.revision), ("changed", 5))
        # The window can also end between the two reads.
        self.schedule()
        times = iter((T + 299 * SECOND, T + 300 * SECOND))
        self.assertEqual(SchedulerService(self.database, clock=lambda _c: next(times)).once().code, "changed")
        self.assertEqual(self.counts()["refresh_runs"], 0)

    def test_save_waits_for_admission_and_cannot_change_its_revision(self):
        # The scheduler holds the settings share lock until commit. A PUT
        # that starts during admission waits, so the run keeps revision 4.
        self.schedule()
        admin = self.login("admin")
        results = {}

        def slow_clock(connection):
            # The second call runs inside the write transaction, after the
            # locks. Start a PUT from another thread and give it time to wait.
            results.setdefault("calls", 0)
            results["calls"] += 1
            if results["calls"] == 2:
                import threading
                thread = threading.Thread(target=lambda: results.__setitem__("put", self.client.put(
                    "/api/v1/settings", headers={**admin, "If-Match": '"settings-4"', "Content-Type": "application/json"},
                    json={"schedule_enabled": True, "daily_time": "07:00", "timezone": "America/New_York"})))
                thread.start()
                results["thread"] = thread
                time.sleep(0.5)
                results["waiting"] = thread.is_alive()
            return T + 20 * SECOND

        outcome = SchedulerService(self.database, clock=slow_clock).once()
        results["thread"].join(10)
        self.assertEqual(outcome.code, "admitted")
        self.assertTrue(results["waiting"])
        self.assertEqual(results["put"].status_code, 200)
        run = self.sql("SELECT settings_revision, policy_snapshot FROM refresh_runs")[0]
        self.assertEqual((run["settings_revision"], run["policy_snapshot"]["settings_revision"]), (4, 4))
        self.assertEqual(self.sql("SELECT revision FROM shared_settings")[0]["revision"], 5)

    def test_insert_and_commit_failures_leave_nothing_and_allow_one_retry(self):
        # S15. A BEFORE trigger fails during the insert. A deferred constraint
        # trigger fails only at COMMIT, after every statement succeeded.
        self.schedule()
        for deferred in (False, True):
            with self.subTest(deferred=deferred):
                self.sql("CREATE FUNCTION reject_outbox() RETURNS trigger LANGUAGE plpgsql "
                         "AS $$ BEGIN RAISE EXCEPTION 'synthetic'; END $$")
                trigger = ("CREATE CONSTRAINT TRIGGER reject_outbox AFTER INSERT ON job_outbox "
                           "DEFERRABLE INITIALLY DEFERRED" if deferred
                           else "CREATE TRIGGER reject_outbox BEFORE INSERT ON job_outbox")
                self.sql(trigger + " FOR EACH ROW EXECUTE FUNCTION reject_outbox()")
                try:
                    with self.assertRaises(Problem) as caught:
                        self.once(T + 20 * SECOND)
                    self.assertEqual((caught.exception.status, caught.exception.code), (503, "dependency_unavailable"))
                    self.assertEqual(self.counts(), {"refresh_runs": 0, "job_outbox": 0, "api_commands": 0})
                    self.assertIsNone(self.holder())
                finally:
                    self.sql("DROP TRIGGER reject_outbox ON job_outbox")
                    self.sql("DROP FUNCTION reject_outbox()")
        # The next poll inside the window admits once; a later poll finds it.
        self.assertEqual(self.once(T + 40 * SECOND).code, "admitted")
        self.assertEqual(self.once(T + 55 * SECOND).code, "duplicate")
        self.assertEqual(self.counts()["refresh_runs"], 1)

    def test_two_schedulers_and_manual_start_race(self):
        # S14. Three processes start at the same moment. Manual Start needs
        # one transaction and the scheduler needs two, so manual Start usually
        # wins a true tie. The last attempt delays manual Start by 0.5 seconds
        # so that the branch where a scheduler wins is also exercised.
        winners = []
        for attempt, delay in enumerate((0, 0, 0.5)):
            with self.subTest(attempt=attempt, delay=delay):
                self.tearDown()
                self.setUp()
                self.schedule()
                token = self.login("admin")["Authorization"][7:]
                context = multiprocessing.get_context("spawn")
                ready, result, start = context.Queue(), context.Queue(), context.Event()
                processes = [context.Process(target=scheduler_contender,
                                             args=(DSN, (T + 20 * SECOND).isoformat(), ready, start, result))
                             for _ in range(2)]
                processes.append(context.Process(target=manual_contender, args=(DSN, token, delay, ready, start, result)))
                try:
                    for process in processes:
                        process.start()
                    for _ in processes:
                        ready.get(timeout=20)
                    start.set()
                    outcomes = sorted(result.get(timeout=20) for _ in processes)
                    for process in processes:
                        process.join(10)
                        self.assertEqual(process.exitcode, 0)
                finally:
                    for process in processes:
                        if process.is_alive():
                            process.kill()
                            process.join()
                    ready.close()
                    result.close()
                won = [item for item in outcomes if item[1] in ("accepted", "admitted")]
                self.assertEqual(len(won), 1, outcomes)
                self.assertEqual(self.counts()["refresh_runs"], 1)
                self.assertEqual(self.counts()["job_outbox"], 1)
                self.assertLessEqual(len(self.sql("SELECT id FROM refresh_runs WHERE request_key=%s",
                                                  (occurrence_key(4, T),))), 1)
                if won[0][0] == "manual":
                    self.assertEqual(outcomes[1:], [("scheduler", "blocked", "refresh_active")] * 2)
                else:
                    self.assertEqual(outcomes[0], ("manual", "refresh_blocked", None))
                    losers = [item[1:] for item in outcomes if item[0] == "scheduler" and item[1] != "admitted"]
                    self.assertIn(losers[0], (("duplicate", None), ("blocked", "refresh_active")))
                winners.append(won[0][0])
                if delay:
                    self.assertEqual(won[0][0], "scheduler", outcomes)
        print(f"\nS14 winners by attempt: {winners}", file=sys.stderr)

    def test_worker_role_admits_with_database_clock_and_only_database_setting(self):
        # S17 with the real PostgreSQL clock. Save the current UTC minute as
        # the daily time, so the occurrence is due for about the next 4 minutes.
        now = self.sql("SELECT clock_timestamp() AS now")[0]["now"].astimezone(timezone.utc)
        self.schedule(daily_time=now.strftime("%H:%M"), zone="UTC", updated_at=now - timedelta(days=1))
        backend = Path(__file__).resolve().parents[1]
        # The child gets only PATH, PYTHONPATH and the database URL: no EIA
        # key, S3 credential or Redis URL exists in its environment.
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(backend / "src"), "TRINITY_DATABASE_URL": DSN}
        process = subprocess.Popen([sys.executable, "-m", "trinity.workers", "scheduler"], cwd=backend, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not self.sql("SELECT id FROM refresh_runs"):
                time.sleep(0.2)
        finally:
            process.send_signal(signal.SIGTERM)
            output, errors = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 0, errors)
        run = self.sql("SELECT id, trigger_kind, requested_by FROM refresh_runs")
        self.assertEqual([(row["trigger_kind"], row["requested_by"]) for row in run], [("scheduled", None)])
        lines = [line for line in errors.splitlines() if line.strip()]
        expected = re.compile(r"\S+ \S+ INFO scheduler outcome=admitted revision=4 occurrence=\S+Z "
                              rf"reason=- run_id={run[0]['id']}$")
        self.assertTrue(any(expected.fullmatch(line) for line in lines), errors)
        self.assertTrue(all("scheduler outcome=" in line for line in lines), errors)
        self.assertNotIn(DSN, output + errors)


@unittest.skipUnless(DSN and REDIS_PORT, "Use tests/run_local_refresh_checks.py for real Redis and PostgreSQL")
class SchedulerDispatchTests(PostgresFixture, unittest.TestCase):
    def test_scheduled_run_is_dispatched_by_the_existing_outbox_worker(self):
        # S16. The queue has no consumer, so no refresh worker and no EIA
        # call runs. The check ends when the job waits in Redis.
        self.sql("""UPDATE shared_settings SET setup_completed_at=%s, updated_at=%s, updated_by='test_admin',
            daily_time='06:15', schedule_timezone='America/New_York', schedule_enabled=true, revision=4""",
                 (T - timedelta(days=1), T - timedelta(days=1)))
        admitted = SchedulerService(self.database, clock=at(T + 20 * SECOND)).once()
        self.assertEqual(admitted.code, "admitted")
        connection = {"host": "127.0.0.1", "port": int(REDIS_PORT), "socket_connect_timeout": 2, "socket_timeout": 2}

        async def scenario():
            # A unique queue name keeps this job away from other tests.
            queue = RefreshQueue(connection, name="test-" + uuid4().hex)
            stop = asyncio.Event()
            worker = asyncio.create_task(outbox.run(DispatchService(self.database, queue), stop))
            try:
                for _ in range(100):
                    if self.sql("SELECT status FROM job_outbox")[0]["status"] == "delivered":
                        break
                    await asyncio.sleep(0.1)
                stop.set()
                await asyncio.wait_for(worker, 10)
                payload = self.sql("SELECT payload FROM job_outbox")[0]["payload"]
                job = await queue.queue.getJob(job_id(payload))
                return payload, await queue.state(payload), job.data if job else None
            finally:
                stop.set()
                await queue.queue.obliterate(force=True)
                await queue.close()

        payload, state, data = asyncio.run(scenario())
        self.assertEqual(self.sql("SELECT status FROM job_outbox")[0]["status"], "delivered")
        self.assertEqual((payload["run_id"], payload["dispatch_generation"]), (str(admitted.run_id), 0))
        self.assertEqual((state, data), ("waiting", payload))
        run = self.sql("SELECT trigger_kind, status FROM refresh_runs")[0]
        self.assertEqual(run, {"trigger_kind": "scheduled", "status": "requested"})


if __name__ == "__main__":
    unittest.main()
