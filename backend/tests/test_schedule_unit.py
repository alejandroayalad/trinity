"""Offline checks for daily schedule clock rules and the settings request model.

These tests use fixed instants instead of the system clock. Each clock row
comes from the approved specification. Daylight-saving dates use
America/New_York in 2026: clocks move forward on March 8 and back on
November 1. America/Merida has no daylight-saving time.
"""
from datetime import date, datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from trinity.settings.schedule import (
    DUE_WINDOW_SECONDS, due_occurrence, local_text, next_check, occurrence,
    occurrence_key, valid_timezone,
)
from trinity.auth.schemas import Blocker
from trinity.settings.schemas import ScheduleStatus, SettingsRequest

NEW_YORK = ZoneInfo("America/New_York")


def utc(text):
    """Build an aware UTC datetime from compact ISO text."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def row(daily_time="06:15", zone="America/New_York", *, enabled=True, setup=True,
        updated_at="2026-01-01T00:00:00Z", revision=4):
    """Build a synthetic shared_settings row with the database column names."""
    return {
        "setup_completed_at": utc("2026-01-01T00:00:00Z") if setup else None,
        "schedule_enabled": enabled,
        "daily_time": daily_time,
        "schedule_timezone": zone,
        "revision": revision,
        "updated_at": utc(updated_at),
    }


class OccurrenceTests(unittest.TestCase):
    def test_gap_has_no_occurrence_and_fold_uses_first_instant(self):
        # 02:30 does not exist on March 8. 01:30 happens twice on November 1.
        self.assertIsNone(occurrence(date(2026, 3, 8), "02:30", NEW_YORK))
        self.assertEqual(occurrence(date(2026, 3, 9), "02:30", NEW_YORK), utc("2026-03-09T06:30:00Z"))
        self.assertEqual(occurrence(date(2026, 11, 1), "01:30", NEW_YORK), utc("2026-11-01T05:30:00Z"))

    def test_gap_boundaries(self):
        # 01:59 exists before the jump and 03:00 exists after it.
        self.assertEqual(occurrence(date(2026, 3, 8), "01:59", NEW_YORK), utc("2026-03-08T06:59:00Z"))
        self.assertIsNone(occurrence(date(2026, 3, 8), "02:00", NEW_YORK))
        self.assertEqual(occurrence(date(2026, 3, 8), "03:00", NEW_YORK), utc("2026-03-08T07:00:00Z"))


class NextCheckTests(unittest.TestCase):
    def test_specification_clock_examples(self):
        cases = [
            (row(), "2026-10-05T12:00:00Z", "2026-10-06T10:15:00Z", "2026-10-06T06:15:00-04:00"),
            # An occurrence equal to evaluated_at is not "next"; the next one is tomorrow.
            (row(), "2026-10-05T10:15:00Z", "2026-10-06T10:15:00Z", "2026-10-06T06:15:00-04:00"),
            (row("08:00", "America/Merida"), "2026-10-05T15:00:00Z", "2026-10-06T14:00:00Z",
             "2026-10-06T08:00:00-06:00"),
            (row("02:30"), "2026-03-08T06:00:00Z", "2026-03-09T06:30:00Z", "2026-03-09T02:30:00-04:00"),
            (row("01:30"), "2026-11-01T04:00:00Z", "2026-11-01T05:30:00Z", "2026-11-01T01:30:00-04:00"),
            # After the first 01:30, the second 01:30 (EST) is skipped.
            (row("01:30"), "2026-11-01T05:45:00Z", "2026-11-02T06:30:00Z", "2026-11-02T01:30:00-05:00"),
        ]
        for settings, now, expected_utc, expected_local in cases:
            with self.subTest(now=now, time=settings["daily_time"]):
                result = next_check(utc(now), settings)
                self.assertEqual(result, utc(expected_utc))
                self.assertEqual(local_text(result, settings["schedule_timezone"]), expected_local)

    def test_null_when_not_set_up_or_disabled(self):
        now = utc("2026-10-05T12:00:00Z")
        self.assertIsNone(next_check(now, row(enabled=False)))
        unset = {**row(setup=False, enabled=False), "daily_time": None, "schedule_timezone": None}
        self.assertIsNone(next_check(now, unset))

    def test_naive_now_is_rejected(self):
        # A naive datetime has no offset, so its instant is unknown.
        with self.assertRaises(ValueError):
            next_check(datetime(2026, 10, 5, 12), row())


class DueOccurrenceTests(unittest.TestCase):
    T = utc("2026-10-05T10:15:00Z")

    def test_window_edges(self):
        settings = row()
        self.assertIsNone(due_occurrence(self.T - timedelta(microseconds=1), settings))
        self.assertEqual(due_occurrence(self.T, settings), self.T)
        last = self.T + timedelta(seconds=DUE_WINDOW_SECONDS) - timedelta(microseconds=1)
        self.assertEqual(due_occurrence(last, settings), self.T)
        self.assertIsNone(due_occurrence(self.T + timedelta(seconds=DUE_WINDOW_SECONDS), settings))

    def test_occurrence_must_be_after_the_effective_save(self):
        # A real save at or after T makes T not due. A save before T keeps it due.
        now = self.T + timedelta(seconds=20)
        self.assertIsNone(due_occurrence(now, row(updated_at="2026-10-05T10:15:10Z")))
        self.assertIsNone(due_occurrence(now, row(updated_at="2026-10-05T10:15:00Z")))
        self.assertEqual(due_occurrence(now, row(updated_at="2026-10-05T10:14:59Z")), self.T)

    def test_window_crossing_local_midnight(self):
        # 23:58 local is 03:58Z on the next UTC date. At 00:01 local the local
        # date has changed, but the previous date's occurrence is still due.
        settings = row("23:58")
        expected = utc("2026-10-06T03:58:00Z")
        self.assertEqual(due_occurrence(utc("2026-10-06T04:01:00Z"), settings), expected)

    def test_not_due_when_disabled_not_set_up_or_in_a_gap(self):
        self.assertIsNone(due_occurrence(self.T, row(enabled=False)))
        unset = {**row(setup=False, enabled=False), "daily_time": None, "schedule_timezone": None}
        self.assertIsNone(due_occurrence(self.T, unset))
        # 02:30 on March 8 does not exist, so nothing is due around that time.
        self.assertIsNone(due_occurrence(utc("2026-03-08T07:31:00Z"), row("02:30")))


class KeyTests(unittest.TestCase):
    def test_key_is_stable_and_depends_on_revision_and_instant(self):
        instant = utc("2026-10-05T10:15:00Z")
        key = occurrence_key(4, instant)
        self.assertIsInstance(key, UUID)
        self.assertEqual(key.version, 5)
        # The same instant written with another offset is the same occurrence.
        self.assertEqual(key, occurrence_key(4, instant.astimezone(NEW_YORK)))
        self.assertNotEqual(key, occurrence_key(5, instant))
        self.assertNotEqual(key, occurrence_key(4, instant + timedelta(days=1)))

    def test_invalid_key_input(self):
        for revision in (-1, True, "4"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                occurrence_key(revision, utc("2026-10-05T10:15:00Z"))
        with self.assertRaises(ValueError):
            occurrence_key(4, datetime(2026, 10, 5, 10, 15))


class TimezoneTests(unittest.TestCase):
    def test_exact_iana_names_only(self):
        for name in ("UTC", "America/Merida", "America/New_York"):
            with self.subTest(name=name):
                self.assertTrue(valid_timezone(name))
        # A case variant can load on macOS, but it is not an IANA name.
        for name in ("america/new_york", "posix/America/New_York", "localtime", "/etc/localtime",
                     "America/Nowhere", "", "A" * 101, None, 5):
            with self.subTest(name=name):
                self.assertFalse(valid_timezone(name))

    def test_localtime_is_rejected_when_the_runtime_lists_it(self):
        # The Linux API image lists "localtime" in available_timezones(), and
        # ZoneInfo("localtime") loads there. macOS has neither. Simulate both
        # so that only the explicit guard can reject the name; without the
        # guard this test fails on macOS too.
        from trinity.settings import schedule
        linux_like = schedule._known_timezones() | {"localtime"}
        with patch.object(schedule, "_known_timezones", lambda: linux_like), \
                patch.object(schedule, "ZoneInfo", lambda name: ZoneInfo("UTC")):
            self.assertFalse(valid_timezone("localtime"))
            self.assertTrue(valid_timezone("America/New_York"))


class SettingsRequestTests(unittest.TestCase):
    VALID = {"schedule_enabled": True, "daily_time": "06:15", "timezone": "America/New_York"}

    def parse(self, body):
        """Validate decoded JSON in the same way the route will."""
        return SettingsRequest.model_validate(json.loads(json.dumps(body)))

    def test_valid_bodies_including_disabled(self):
        self.assertEqual(self.parse(self.VALID).timezone, "America/New_York")
        self.assertFalse(self.parse({**self.VALID, "schedule_enabled": False}).schedule_enabled)

    def test_rejected_bodies(self):
        bad = [
            {k: v for k, v in self.VALID.items() if k != "daily_time"},
            {k: v for k, v in self.VALID.items() if k != "timezone"},
            {k: v for k, v in self.VALID.items() if k != "schedule_enabled"},
            {**self.VALID, "publication_mode": "automatic"},
            {**self.VALID, "revision": "4"},
            {**self.VALID, "updated_by": "user_example_admin"},
            {**self.VALID, "setup_completed_at": "2026-10-05T12:00:00Z"},
            # Strict mode: no string or integer stands in for a boolean.
            {**self.VALID, "schedule_enabled": "true"},
            {**self.VALID, "schedule_enabled": 1},
            {**self.VALID, "schedule_enabled": None},
            {**self.VALID, "daily_time": None},
            {**self.VALID, "timezone": None},
        ]
        for time_value in ("24:00", "6:15", "06:60", "06:15\n", "06:15:00", ""):
            bad.append({**self.VALID, "daily_time": time_value})
        for zone in ("America/Nowhere", "america/new_york", "posix/America/New_York", "/etc/localtime", "A" * 101):
            bad.append({**self.VALID, "timezone": zone})
        for body in bad:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                self.parse(body)


class ScheduleStatusTests(unittest.TestCase):
    BASE = {"settings_revision": "4", "schedule_enabled": True, "timezone": "America/New_York",
            "evaluated_at": utc("2026-10-05T12:00:00Z")}

    def test_valid_status_serializes_utc_with_z(self):
        status = ScheduleStatus(**self.BASE, next_check_at=utc("2026-10-06T10:15:00Z"),
                                next_check_local="2026-10-06T06:15:00-04:00", eligible_now=True, blocker=None)
        body = json.loads(status.model_dump_json())
        self.assertEqual(body["next_check_at"], "2026-10-06T10:15:00Z")
        self.assertEqual(body["evaluated_at"], "2026-10-05T12:00:00Z")

    def test_inconsistent_status_is_rejected(self):
        # Build a real Blocker so the test fails only on the consistency rule.
        blocker = Blocker(code="refresh_active", message="A refresh is running.",
                          run_id=None, version_id=None, warning_id=None)
        bad = [
            {"next_check_at": utc("2026-10-06T10:15:00Z"), "next_check_local": None,
             "eligible_now": True, "blocker": None},
            {"next_check_at": utc("2026-10-05T12:00:00Z"), "next_check_local": "2026-10-05T08:00:00-04:00",
             "eligible_now": True, "blocker": None},
            {"next_check_at": None, "next_check_local": None, "eligible_now": True, "blocker": blocker},
            {"next_check_at": None, "next_check_local": None, "eligible_now": False, "blocker": None},
        ]
        for fields in bad:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                ScheduleStatus(**self.BASE, **fields)


if __name__ == "__main__":
    unittest.main()
