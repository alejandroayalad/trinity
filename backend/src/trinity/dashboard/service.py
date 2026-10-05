"""Authorize national reads and reuse the shared preview execution lifecycle."""

import time

from trinity.auth.permissions import require
from trinity.auth.repository import resolve_session
from trinity.catalog.schemas import Freshness, LastRefresh
from trinity.contracts.queries import PreviewOperation
from trinity.dashboard.calculation import (
    build_dashboard, build_metric, parse_dashboard_input, parse_metric_input,
    resolve_range, validate_dashboard_input,
)
from trinity.dashboard.schemas import DateRange
from trinity.errors import Problem
from trinity.publication.repository import read_pinned_publication, read_preview_publication
from trinity.queries import repository
from trinity.queries.service import PreparedPreview, QueryDeadline
from trinity.refresh.repository import read_last_refresh


class RefusingCodec:
    """Refuse pagination: a national read has room for every requested date."""

    def encode(self, *args, **kwargs):
        """Fail closed if the shared preview builder tries to sign more rows."""
        raise ValueError('National response cannot have a cursor')


class NationalService:
    """Bind identity, publication, evidence and freshness before national execution.

    Routes supply the session token, decoded pairs and buffered body. Reject
    identity and shape failures before the shared rate debit. Keep that debit
    for later failures. Read publication, evidence authority and freshness in
    one snapshot, then close it before execution. The shared execution owner
    retains reservations until cleanup is confirmed, including after failure.
    Return a complete validated response; never activate or edit a publication.
    """

    def __init__(self, database, execution_factory):
        """Accept the shared database adapter and lazy preview execution factory."""
        self.database = database
        self.execution_factory = execution_factory

    def _prepare(self, token, pairs, *, metric=False, body=b'', cancelled=None):
        """Keep the accepted debit order and use separate preflight/execution budgets."""
        preflight = QueryDeadline(15)
        preflight.cancelled = cancelled
        with self.database.transaction(preflight, readonly=True) as connection:
            first = resolve_session(connection, token)
            require(first, 'national:read')
        parser = parse_metric_input if metric else parse_dashboard_input
        request = parser(pairs, body=body)

        # Commit this attempt before checking combinations or publication state.
        # A malformed date costs nothing; a valid but reversed range costs one.
        with self.database.transaction(preflight, error_code='dependency_unavailable') as connection:
            retry = repository.reserve_rate(connection, first.user_id)
        if retry is not None:
            raise Problem(429, 'rate_limited', retry_after=retry)
        if not metric:
            validate_dashboard_input(request)

        # The database adapter uses REPEATABLE READ for a read-only transaction.
        # All three readers therefore describe the same publication snapshot.
        with self.database.transaction(preflight, readonly=True, error_code='dependency_unavailable') as connection:
            second = resolve_session(connection, token)
            require(second, 'national:read')
            if first.user_id != second.user_id or first.session_id != second.session_id:
                raise Problem(401, 'invalid_session')
            pinned = read_pinned_publication(connection)
            if pinned is None:
                raise Problem(409, 'data_unavailable')
            pinned = read_preview_publication(connection, pinned)
            try:
                row = read_last_refresh(connection)
                freshness = Freshness(
                    latest_observation_date=pinned.publication.latest_observation_date,
                    published_at=pinned.publication.published_at,
                    last_refresh=LastRefresh(**row) if row is not None else None,
                )
            except (ValueError, TypeError, KeyError):
                raise Problem(503, 'dependency_unavailable') from None

        selected = (DateRange(start=request.period, end=request.period) if metric
                    else resolve_range(request, pinned.publication.latest_observation_date))
        operation = PreviewOperation(
            'national', str(pinned.publication.publication_event_id), str(pinned.publication.version_id),
            selected.start.isoformat(), selected.end.isoformat(),
            page_size=(selected.end - selected.start).days + 1,
        )
        execution = self.execution_factory()
        try:
            preflight.remaining()
            started = time.monotonic()
            deadline = QueryDeadline(30)
            deadline.cancelled = cancelled
            with self.database.transaction(deadline, error_code='dependency_unavailable') as connection:
                reservation = repository.reserve_capacity(
                    connection, second.user_id, pinned, execution.deployment_id,
                    execution.daemon_id, deadline.remaining(),
                )
            if reservation is None:
                raise Problem(429, 'rate_limited', retry_after=1)
        except Exception:
            execution.close()
            raise
        prepared = PreparedPreview(operation, pinned, reservation, deadline, started, RefusingCodec())
        return prepared, execution, freshness

    def _execute(self, token, pairs, *, metric=False, body=b'', cancelled=None):
        """Accept a complete shared preview only after its execution owner returns."""
        prepared, execution, freshness = self._prepare(
            token, pairs, metric=metric, body=body, cancelled=cancelled,
        )
        preview = execution.execute(prepared)
        # Reject an adapter that returns another valid page for the wrong pin or
        # range. Model validation alone cannot establish the requested identity.
        if (preview.publication != prepared.pinned.publication
                or preview.range.start.isoformat() != prepared.query.start
                or preview.range.end.isoformat() != prepared.query.end):
            raise Problem(503, 'dependency_unavailable')
        return build_metric(preview) if metric else build_dashboard(preview, freshness)

    def dashboard(self, token, pairs, *, body=b'', cancelled=None):
        """Return all selected dates with cards for the selected end date."""
        return self._execute(token, pairs, body=body, cancelled=cancelled)

    def metric(self, token, pairs, *, body=b'', cancelled=None):
        """Return the dashboard calculation for one strictly requested date."""
        return self._execute(token, pairs, metric=True, body=body, cancelled=cancelled)
