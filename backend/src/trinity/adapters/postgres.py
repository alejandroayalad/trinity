"""Bound PostgreSQL work and keep service transactions explicit."""

from contextlib import contextmanager
import logging
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout, PoolClosed, TooManyRequests

from trinity.errors import Problem


class Deadline:
    """Track one operation budget across connection, SQL and password work."""

    def __init__(self, seconds: float = 15):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        """Return remaining seconds or fail closed after expiry."""
        left = self.end - time.monotonic()
        if left <= 0:
            raise Problem(503, "auth_unavailable")
        return left


class _SafePoolLog(logging.Filter):
    def filter(self, record):
        record.msg = "PostgreSQL pool connection event."
        record.args = ()
        record.exc_info = None
        return True


class Database:
    """Own a bounded pool; construction does not open connections."""

    def __init__(self, settings):
        logger = logging.getLogger("psycopg.pool")
        if not any(isinstance(item, _SafePoolLog) for item in logger.filters):
            logger.addFilter(_SafePoolLog())
        self.pool = ConnectionPool(
            settings.database_url.get_secret_value(), min_size=0, max_size=4,
            timeout=5, max_waiting=16, open=False,
            kwargs={"autocommit": True, "row_factory": dict_row, "connect_timeout": 5, "options": "-c timezone=UTC"},
        )

    def open(self):
        """Allow lazy connections without making liveness depend on availability."""
        self.pool.open(wait=False)

    def close(self):
        """Release the pool at API shutdown."""
        self.pool.close(timeout=5)

    @contextmanager
    def transaction(self, deadline: Deadline, *, readonly=False, error_code="auth_unavailable"):
        """Commit only successful service work; sanitize all persistence failures."""
        try:
            with self.pool.connection(timeout=min(5, deadline.remaining())) as connection:
                with connection.transaction():
                    if readonly:
                        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    millis = max(1, int(min(5, deadline.remaining()) * 1000))
                    connection.execute("SELECT set_config('statement_timeout', %s, true), "
                                       "set_config('lock_timeout', %s, true), "
                                       "set_config('transaction_timeout', %s, true)",
                                       (str(millis), str(millis), str(millis)))
                    yield connection
                    deadline.remaining()
        except Problem:
            raise
        except (psycopg.Error, PoolTimeout, PoolClosed, TooManyRequests):
            raise Problem(503, error_code) from None
