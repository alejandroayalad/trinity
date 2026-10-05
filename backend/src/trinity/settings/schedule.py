"""Calculate daily schedule occurrences without reading the database or the clock.

This module is the single source of the clock rules for the Schedule status
route and the scheduler worker. Both callers pass the saved settings row and
a "now" instant that they read from PostgreSQL. This module only calculates.
It does not read settings, lock rows, start refreshes or read the system clock.

Terms used in this module:

- An occurrence is the instant in UTC when one local calendar date reaches
  the saved `daily_time` in the saved timezone.
- A gap is a local time that does not exist, because daylight-saving time
  moves clocks forward. That date has no occurrence.
- A fold is a local time that happens twice, because daylight-saving time
  moves clocks back. Only the first UTC instant is an occurrence.

Callers receive aware UTC datetimes, or None when no occurrence applies.
Invalid input raises ValueError. The caller decides how to report it.
"""
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import re
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

# The scheduler admits an occurrence only during this many seconds after it.
# Example: an occurrence at 10:15:00Z is due at 10:19:59Z and missed at 10:20:00Z.
DUE_WINDOW_SECONDS = 300

# uuid5 builds the same UUID from the same namespace and text on every run.
# The scheduler uses it as `refresh_runs.request_key`, so the namespace must
# never change. A new value would let one occurrence create a second run.
SCHEDULE_NAMESPACE = UUID("ac3f96ff-a718-49b4-8f8d-193d78fb648a")

# The pattern accepts 00:00 to 23:59 with two digits for each part.
# "06:15" is accepted. "6:15" and "24:00" are rejected.
_DAILY_TIME = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset[str]:
    """Return the IANA names of the running Python once per process.

    available_timezones() scans the timezone files on each call, so the
    result is cached. The set contains canonical names and links such as
    "US/Eastern". It does not contain "posix/..." or "right/..." copies.
    """
    return frozenset(available_timezones())


def valid_timezone(name: object) -> bool:
    """Return True only for an exact, loadable IANA timezone name.

    ZoneInfo(name) alone is not enough. On a case-insensitive file system,
    ZoneInfo("america/new_york") loads, but that name is not an IANA name.
    Require an exact, case-sensitive member of the known set, and then
    require that ZoneInfo can load it.

    Example: "America/Merida" is valid. "america/merida" and
    "posix/America/Merida" are not valid.
    """
    if not isinstance(name, str) or not 1 <= len(name) <= 100:
        return False
    # Debian's tzdata adds "localtime", a link to /etc/localtime, and
    # available_timezones() lists it in the Linux API image. Its meaning
    # depends on the container configuration, so it is not a fixed zone.
    # macOS does not list it, so only this guard rejects it everywhere.
    if name == "localtime":
        return False
    if name not in _known_timezones():
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def parse_daily_time(value: str) -> time:
    """Convert an "HH:mm" string to a time, or raise ValueError.

    fullmatch requires the whole string to match, so "06:15\\n" and
    "06:15:00" are rejected.
    """
    match = _DAILY_TIME.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError("daily_time must be HH:mm")
    return time(int(match.group(1)), int(match.group(2)))


def _require_utc(value: datetime, name: str) -> datetime:
    """Reject naive datetimes and return the same instant in UTC.

    A naive datetime has no offset. Comparing it with aware datetimes would
    raise TypeError or use the wrong instant, so it is rejected.
    """
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be an aware datetime")
    return value.astimezone(timezone.utc)


def occurrence(day: date, daily_time: str, zone: ZoneInfo) -> datetime | None:
    """Return the UTC occurrence for one local date, or None for a gap.

    Input: a local calendar date, the saved "HH:mm" time and the saved zone.
    Result: an aware UTC datetime, or None when that local time does not exist.

    Example in America/New_York: 2026-03-08 at 02:30 returns None, because
    clocks move from 02:00 to 03:00. 2026-11-01 at 01:30 returns 05:30Z, the
    first of the two 01:30 instants.
    """
    wall = datetime.combine(day, parse_daily_time(daily_time))
    # fold=0 selects the earlier instant when a local time happens twice.
    # Python also accepts a time inside a gap and gives it an offset. Convert
    # to UTC and back: a gap time does not return to the same wall time.
    local = wall.replace(tzinfo=zone, fold=0)
    instant = local.astimezone(timezone.utc)
    if instant.astimezone(zone).replace(tzinfo=None) != wall:
        return None
    return instant


def _active(row) -> bool:
    """Return True when setup is complete and the daily schedule is on."""
    return row["setup_completed_at"] is not None and row["schedule_enabled"] is True


def next_check(now: datetime, row) -> datetime | None:
    """Return the first occurrence strictly after now, or None.

    Input: "now" from PostgreSQL and a `shared_settings` row (a mapping).
    Result: None when setup is not complete or the schedule is off.
    Otherwise the first occurrence later than now, even when a refresh
    blocker exists. An occurrence equal to now is not returned, because
    the status must describe a future check.
    """
    now = _require_utc(now, "now")
    if not _active(row):
        return None
    zone = ZoneInfo(row["schedule_timezone"])
    first_day = now.astimezone(zone).date()
    # The occurrence on today's local date can be in the past, and a gap
    # removes at most one date. Three dates always contain the answer.
    for offset in range(3):
        instant = occurrence(first_day + timedelta(days=offset), row["daily_time"], zone)
        if instant is not None and instant > now:
            return instant
    raise ValueError("no occurrence found in three local dates")


def due_occurrence(now: datetime, row, window: int = DUE_WINDOW_SECONDS) -> datetime | None:
    """Return the occurrence the scheduler may admit now, or None.

    An occurrence T is due when both rules are true:

    - T <= now < T + window. After the window, T is missed and skipped.
    - T > row["updated_at"]. A saved change applies only to later
      occurrences. A no-op save keeps updated_at, so it does not cancel T.

    Example with a 300-second window and T = 10:15:00Z: now = 10:15:00Z and
    10:19:59Z return T; now = 10:20:00Z returns None.
    """
    now = _require_utc(now, "now")
    if not _active(row):
        return None
    updated_at = _require_utc(row["updated_at"], "updated_at")
    zone = ZoneInfo(row["schedule_timezone"])
    span = timedelta(seconds=window)
    # A due T lies in (now - window, now]. Its local date is the local date
    # of one of these two instants. Occurrences are about one day apart,
    # so at most one candidate can match.
    days = sorted({(now - span).astimezone(zone).date(), now.astimezone(zone).date()})
    for day in days:
        instant = occurrence(day, row["daily_time"], zone)
        if instant is not None and instant <= now < instant + span and instant > updated_at:
            return instant
    return None


def occurrence_key(revision: int, instant: datetime) -> UUID:
    """Return the stable run key for one (settings revision, occurrence).

    Every scheduler process derives the same key for the same pair. The
    unique `refresh_runs.request_key` then allows only one run per pair.
    A new settings revision gives a new key, as the data contract requires.
    """
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a nonnegative integer")
    stamp = _require_utc(instant, "instant").strftime("%Y-%m-%dT%H:%M:%SZ")
    return uuid5(SCHEDULE_NAMESPACE, f"scheduled:{revision}:{stamp}")


def local_text(instant: datetime, zone_name: str) -> str:
    """Return an instant as RFC 3339 text in the saved zone, with its offset.

    Example: 2026-10-06T10:15:00Z in America/New_York returns
    "2026-10-06T06:15:00-04:00".
    """
    instant = _require_utc(instant, "instant")
    return instant.astimezone(ZoneInfo(zone_name)).isoformat(timespec="seconds")
