"""Authorize filter choices through the shared analytical execution boundary."""

from dataclasses import replace
import time

from trinity.auth.repository import resolve_session
from trinity.errors import Problem
from trinity.publication.repository import read_pinned_publication
from trinity.queries import repository
from trinity.queries.choices import (
    ChoiceCursorCodec, authorize_choices, parse_choice_input, resolve_choices,
)
from trinity.queries.cursors import load_cursor_keys
from trinity.queries.preview import validate_filters
from trinity.queries.service import PreparedPreview, QueryDeadline


class ChoiceService:
    """Turn an authenticated filter request into one supervised distinct page.

    Authorize before primitive parsing, commit the shared rate debit, then
    validate semantics and bookmarks. Recheck the session before pinning one
    active publication. Reserve the same capacity as SQL and preview; execute
    only verified published files in the existing isolated runtime. A failure
    returns no partial choices and never changes publication state.
    """
    def __init__(self, database, execution_factory, *, codec_factory=None):
        self.database = database
        self.execution_factory = execution_factory
        self.codec_factory = codec_factory or (lambda: ChoiceCursorCodec(load_cursor_keys()))

    def prepare(self, token, dataset_key, choice, pairs, *, body=b'', cancelled=None):
        """Close metadata transactions before storage and retain counted failures."""
        preflight = QueryDeadline(15)
        preflight.cancelled = cancelled
        with self.database.transaction(preflight, readonly=True) as connection:
            first = resolve_session(connection, token)
            dataset = authorize_choices(first, dataset_key, choice)
        request = parse_choice_input(pairs, choice, body=body)
        with self.database.transaction(preflight, error_code='dependency_unavailable') as connection:
            retry = repository.reserve_rate(connection, first.user_id)
        if retry is not None:
            raise Problem(429, 'rate_limited', retry_after=retry)
        validate_filters(dataset, request.preview)
        if choice == 'generators' and request.preview.facility is None:
            raise Problem(422, 'invalid_request')
        codec = self.codec_factory()
        position = codec.decode(request.preview.cursor) if request.preview.cursor is not None else None
        if position is not None and (position.dataset != dataset or position.choice != choice):
            raise Problem(422, 'invalid_cursor')
        with self.database.transaction(preflight, readonly=True, error_code='dependency_unavailable') as connection:
            second = resolve_session(connection, token)
            authorize_choices(second, dataset_key, choice)
            if first.user_id != second.user_id or first.session_id != second.session_id:
                raise Problem(401, 'invalid_session')
            pinned = read_pinned_publication(connection)
            # A bookmark cannot select an older publication, even when the
            # caller omits dates and would otherwise receive new defaults.
            if position is not None and (pinned is None or
                    position.publication_event_id != str(pinned.publication.publication_event_id)):
                raise Problem(409, 'publication_changed')
            if pinned is None:
                raise Problem(409, 'data_unavailable')
            operation = resolve_choices(dataset, choice, request, pinned.publication)
            if position is not None:
                if replace(position, after=None) != operation:
                    raise Problem(422, 'invalid_cursor')
                operation = position
        execution = self.execution_factory()
        try:
            preflight.remaining()
            started = time.monotonic()
            deadline = QueryDeadline(30)
            deadline.cancelled = cancelled
            with self.database.transaction(deadline, error_code='dependency_unavailable') as connection:
                reservation = repository.reserve_capacity(connection, second.user_id, pinned,
                                    execution.deployment_id, execution.daemon_id, deadline.remaining())
            if reservation is None:
                raise Problem(429, 'rate_limited', retry_after=1)
        except Exception:
            execution.close()
            raise
        return PreparedPreview(operation, pinned, reservation, deadline, started, codec), execution

    def execute(self, token, dataset_key, choice, pairs, *, body=b'', cancelled=None):
        """Return choices only after the supervisor stops and cleans execution."""
        prepared, execution = self.prepare(token, dataset_key, choice, pairs, body=body, cancelled=cancelled)
        return execution.execute(prepared)
