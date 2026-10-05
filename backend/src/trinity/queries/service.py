"""Authorize, debit, validate and pin queries before any staging or execution."""

from dataclasses import dataclass
import time

from trinity.adapters.postgres import Deadline
from trinity.auth.permissions import require
from trinity.auth.repository import resolve_session
from trinity.errors import Problem
from trinity.publication.repository import read_pinned_publication
from trinity.queries.policy import validate_in_process
from trinity.queries.runtime.sql_policy import SQLValidationError
from trinity.queries import repository


class QueryDeadline(Deadline):
    """Keep the original analytical budget across dependencies and retries."""
    cancelled = None

    def remaining(self):
        if self.cancelled is not None and self.cancelled.is_set():
            raise Problem(504, 'query_timeout')
        left = self.end - time.monotonic()
        if left <= 0:
            raise Problem(504, 'query_timeout')
        return left


@dataclass(frozen=True)
class PreparedQuery:
    """Bind accepted caller authority, immutable publication and reservation."""
    query: object
    pinned: object
    reservation: dict
    deadline: QueryDeadline
    started: float


class QueryService:
    """Own short transactions; never keep auth snapshots open during execution."""
    def __init__(self, database, execution_factory, *, policy=validate_in_process):
        self.database, self.execution_factory, self.policy = database, execution_factory, policy

    def prepare(self, token, sql, *, cancelled=None):
        """Deny Viewer before counters/parser/configuration; preserve counted failures."""
        started = time.monotonic()
        deadline = QueryDeadline(30)
        deadline.cancelled = cancelled
        with self.database.transaction(deadline, readonly=True) as connection:
            first = resolve_session(connection, token)
            require(first, 'sql:execute')
        with self.database.transaction(deadline, error_code='dependency_unavailable') as connection:
            retry = repository.reserve_rate(connection, first.user_id)
        if retry is not None:
            raise Problem(429, 'rate_limited', retry_after=retry)
        try:
            query = self.policy(sql, timeout=min(2, deadline.remaining()))
        except SQLValidationError:
            raise Problem(422, 'sql_not_allowed') from None
        with self.database.transaction(deadline, readonly=True, error_code='dependency_unavailable') as connection:
            second = resolve_session(connection, token)
            require(second, 'sql:execute')
            if first.user_id != second.user_id or first.session_id != second.session_id:
                raise Problem(401, 'invalid_session')
            pinned = read_pinned_publication(connection)
        if pinned is None:
            raise Problem(409, 'data_unavailable')
        execution = self.execution_factory()
        try:
            with self.database.transaction(deadline, error_code='dependency_unavailable') as connection:
                reservation = repository.reserve_capacity(connection, second.user_id, pinned,
                                    execution.deployment_id, execution.daemon_id, deadline.remaining())
            if reservation is None:
                raise Problem(429, 'rate_limited', retry_after=1)
        except Exception:
            execution.close()
            raise
        return PreparedQuery(query,pinned,reservation,deadline,started), execution

    def execute(self, token, sql, *, cancelled=None):
        """Return only a complete, stopped and cleaned query result."""
        prepared, execution = self.prepare(token, sql, cancelled=cancelled)
        return execution.execute(prepared)


@dataclass(frozen=True)
class PreparedPreview(PreparedQuery):
    """Retain signing authority in the API; never send it to the runtime."""
    codec: object
    context: object = None


class PreviewService:
    """Authorize and debit a page, then pin its publication and shared capacity."""
    def __init__(self, database, execution_factory, *, codec_factory=None):
        from trinity.queries.cursors import CursorCodec, load_cursor_keys
        self.database = database
        self.execution_factory = execution_factory
        self.codec_factory = codec_factory or (lambda: CursorCodec(load_cursor_keys()))

    def authorize(self, principal, dataset_key):
        """Apply current dataset authority before parsing input or touching counters."""
        from trinity.queries.preview import authorize_preview
        return authorize_preview(principal, dataset_key)

    def parse_input(self, pairs, *, body):
        """Parse preview input; national reads override only their public grammar."""
        from trinity.queries.preview import parse_preview_input
        return parse_preview_input(pairs, body=body)

    def validate_input(self, dataset, request):
        """Check cross-field rules after the shared rate debit."""
        from trinity.queries.preview import validate_filters
        validate_filters(dataset, request)

    def resolve_input(self, dataset, request, latest):
        """Resolve defaults from the pinned publication, never from a second read."""
        from trinity.queries.preview import resolve_preview
        return resolve_preview(dataset, request, latest)

    def read_context(self, connection, pinned):
        """Allow a national response to pin safe metadata in this same snapshot."""
        return None

    def decode_position(self, codec, request):
        """Authenticate a preview bookmark without treating it as authority."""
        return codec.decode(request.cursor) if request.cursor is not None else None

    def resolve_position(self, position, dataset, request, publication):
        """Bind continuation to the current publication and complete filter tuple."""
        from trinity.queries.cursors import resolve_continuation
        return resolve_continuation(position, dataset, request, publication)

    def operation(self, dataset, pinned, resolved, position):
        """Create the closed operation after authority and publication are pinned."""
        from trinity.contracts.queries import PreviewOperation
        return PreviewOperation(dataset, str(pinned.publication.publication_event_id),
                                str(pinned.publication.version_id), resolved.start.isoformat(),
                                resolved.end.isoformat(), resolved.facility, resolved.generator,
                                resolved.limit, position.after if position is not None else None)

    def prepare(self, token, dataset_key, pairs, *, body=b'', cancelled=None):
        """Commit one debit after identity/shape checks, even if later checks fail.

        Reauthorize before pinning the active version and its frozen evidence.
        Close metadata transactions before any storage or engine work. Start the
        analytical budget immediately before capacity admission; preflight uses
        a separate bounded deadline. No rejection changes publication state.
        """
        from trinity.publication.repository import read_preview_publication
        preflight = QueryDeadline(15)
        preflight.cancelled = cancelled
        with self.database.transaction(preflight, readonly=True) as connection:
            first = resolve_session(connection, token)
            dataset = self.authorize(first, dataset_key)
        request = self.parse_input(pairs, body=body)
        with self.database.transaction(preflight, error_code='dependency_unavailable') as connection:
            retry = repository.reserve_rate(connection, first.user_id)
        if retry is not None:
            raise Problem(429, 'rate_limited', retry_after=retry)
        self.validate_input(dataset, request)
        codec = self.codec_factory()
        position = self.decode_position(codec, request)
        if position is not None and position.request.dataset != dataset:
            raise Problem(422, 'invalid_cursor')
        with self.database.transaction(preflight, readonly=True, error_code='dependency_unavailable') as connection:
            second = resolve_session(connection, token)
            self.authorize(second, dataset_key)
            if first.user_id != second.user_id or first.session_id != second.session_id:
                raise Problem(401, 'invalid_session')
            pinned = read_pinned_publication(connection)
            if position is not None:
                resolved = self.resolve_position(position, dataset, request, pinned.publication if pinned else None)
            elif pinned is None:
                raise Problem(409, 'data_unavailable')
            else:
                resolved = self.resolve_input(dataset, request, pinned.publication.latest_observation_date)
            pinned = read_preview_publication(connection, pinned)
            context = self.read_context(connection, pinned)
        operation = self.operation(dataset, pinned, resolved, position)
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
        return PreparedPreview(operation, pinned, reservation, deadline, started, codec, context), execution

    def execute(self, token, dataset_key, pairs, *, body=b'', cancelled=None):
        """Return the page only after the shared supervisor confirms cleanup."""
        prepared, execution = self.prepare(token, dataset_key, pairs, body=body, cancelled=cancelled)
        return execution.execute(prepared)
