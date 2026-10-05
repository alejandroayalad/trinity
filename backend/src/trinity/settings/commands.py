"""Save shared schedule intent atomically without starting analytical or refresh work."""
from datetime import datetime, time, timedelta, timezone
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import StrictBool, field_validator

from trinity.adapters.postgres import Deadline
from trinity.auth.schemas import StrictModel, Blocker
from trinity.errors import Problem
from trinity.refresh.repository import lock_control, read_context
from trinity.refresh.service import _authorize, admin_context
from trinity.settings.repository import read_settings
from trinity.settings.service import get_settings


class SettingsInput(StrictModel):
    """Require all three fields, including when the schedule is disabled."""
    schedule_enabled: StrictBool
    daily_time: str
    timezone: str

    @field_validator('daily_time')
    @classmethod
    def valid_time(cls, value):
        """Accept HH:mm only; reject coercion, seconds and impossible clock times."""
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
            raise ValueError('Invalid daily time')
        return value

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        """Verify the installed IANA zone database; retain the selected name."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Invalid timezone') from None
        return value


def next_check(now, daily_time, zone):
    """Find the next valid wall-clock occurrence strictly after now.

    A repeated clock time uses fold=0, the first UTC occurrence. A nonexistent
    spring-forward time fails the UTC round trip and is skipped for that day.
    """
    zone = ZoneInfo(zone)
    local = now.astimezone(zone)
    hour, minute = map(int, daily_time.split(':'))
    for offset in range(370):
        day = local.date() + timedelta(days=offset)
        candidate = datetime.combine(day, time(hour, minute), tzinfo=zone).replace(fold=0)
        utc = candidate.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
            continue
        if utc > now:
            return utc, candidate.isoformat()
    raise Problem(503, 'dependency_unavailable')


def schedule_view(settings, context, now):
    """Report clock information independently from the current admission blocker."""
    completed = settings['setup_completed_at'] is not None
    enabled = settings['schedule_enabled']
    code = 'setup_required' if not completed else 'schedule_disabled' if not enabled else None
    blocker = (Blocker(code=code, message='Complete setup.' if not completed else 'The schedule is disabled.',
                       run_id=None, version_id=None, warning_id=None) if code else context.refresh_blocker)
    at, local = next_check(now, settings['daily_time'], settings['schedule_timezone']) if completed and enabled else (None, None)
    return dict(settings_revision=str(settings['revision']), schedule_enabled=enabled,
                next_check_at=at, next_check_local=local, timezone=settings['schedule_timezone'],
                evaluated_at=now, eligible_now=blocker is None, blocker=blocker)


class SettingsService:
    """Own write transactions so an ETag, setup time and actor commit together."""
    def __init__(self, database):
        self.database = database

    def save(self, token, body, etags, pairs=()):
        """Authorize first, then compare the locked revision before writing."""
        with self.database.transaction(Deadline(), error_code='dependency_unavailable') as connection:
            _authorize(connection, token, 'settings:write')
            if pairs:
                raise Problem(422, 'invalid_request')
            try:
                decoded = json.loads(body)
            except (ValueError, UnicodeError, RecursionError):
                raise Problem(400, 'invalid_json') from None
            try:
                value = SettingsInput.model_validate(decoded)
            except ValueError:
                raise Problem(422, 'invalid_request') from None
            if not etags:
                raise Problem(428, 'precondition_required')
            if len(etags) != 1 or not re.fullmatch(r'"settings-(0|[1-9][0-9]*)"', etags[0]):
                raise Problem(422, 'invalid_request')
            lock_control(connection)
            actor = _authorize(connection, token, 'settings:write', lock=True)
            connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR UPDATE')
            current = read_settings(connection)
            if etags[0] != f'"settings-{current["revision"]}"':
                raise Problem(412, 'revision_mismatch')
            # COALESCE retains the first setup completion on every later edit.
            connection.execute('''UPDATE shared_settings SET schedule_enabled=%s,daily_time=%s,
                schedule_timezone=%s,setup_completed_at=COALESCE(setup_completed_at,clock_timestamp()),
                revision=revision+1,updated_at=clock_timestamp(),updated_by=%s WHERE id=1''',
                (value.schedule_enabled, value.daily_time, value.timezone, actor.user_id))
            result = get_settings(actor, connection)
        return result

    def status(self, token, pairs=(), *, body=b''):
        """Read one authorized settings/lifecycle snapshot with database time."""
        with self.database.transaction(Deadline(), readonly=True, error_code='dependency_unavailable') as connection:
            _authorize(connection, token, 'settings:read')
            if pairs or body:
                raise Problem(422, 'invalid_request')
            settings = read_settings(connection)
            context = admin_context(settings, *read_context(connection))
            now = connection.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            return schedule_view(settings, context, now)
