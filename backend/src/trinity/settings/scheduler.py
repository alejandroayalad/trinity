"""Admit due future schedule occurrences through the same durable refresh outbox."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from trinity.adapters.postgres import Deadline
from trinity.refresh.repository import accept_run, lock_control, read_context
from trinity.refresh.service import admin_context
from trinity.settings.commands import next_check
from trinity.settings.repository import read_settings


class Scheduler:
    """Skip missed/blocked occurrences; never synthesize a successful refresh."""
    def __init__(self, database):
        self.database = database

    def tick(self, previous, now):
        """Admit at most one occurrence crossed by this short polling interval.

        The shared lock serializes settings edits, manual commands and multiple
        schedulers. The deterministic request key prevents duplicate admission
        even if a finished run released the slot before another scheduler checks.
        """
        if now <= previous or now - previous > timedelta(seconds=60):
            return None
        with self.database.transaction(Deadline(), error_code='dependency_unavailable') as connection:
            lock_control(connection)
            connection.execute('SELECT id FROM shared_settings WHERE id=1 FOR SHARE')
            settings = read_settings(connection)
            if settings['setup_completed_at'] is None or not settings['schedule_enabled']:
                return None
            # A save changes only future clock occurrences. A delayed tick cannot
            # apply newly saved settings to a time before that settings revision.
            lower = max(previous, settings['updated_at'])
            occurrence, _ = next_check(lower, settings['daily_time'], settings['schedule_timezone'])
            if occurrence > now:
                return None
            context = admin_context(settings, *read_context(connection))
            if context.refresh_blocker is not None:
                return None
            key = uuid5(NAMESPACE_URL, f'trinity:schedule:1:{settings["revision"]}:{occurrence.isoformat()}')
            if connection.execute('SELECT id FROM refresh_runs WHERE request_key=%s', (key,)).fetchone():
                return None
            run = accept_run(connection, None, key, None, settings, trigger='scheduled')
            return run['id']


async def run(database, stop):
    """Poll until stopped; restart begins at the current time without backlog."""
    scheduler = Scheduler(database)
    previous = datetime.now(timezone.utc)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
            break
        except TimeoutError:
            pass
        now = datetime.now(timezone.utc)
        await asyncio.to_thread(scheduler.tick, previous, now)
        previous = now
