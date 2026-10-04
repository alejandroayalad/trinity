"""Supervise short-lived policy parsing before any analytical file read."""

from pathlib import Path
import subprocess
import sys
import threading

from trinity.contracts.queries import ValidatedQuery
from trinity.queries.runtime.sql_policy import SQLValidationError

_SLOTS = threading.BoundedSemaphore(2)


def validate_in_process(sql: str, *, timeout: float = 2) -> ValidatedQuery:
    """Return a verified policy message or terminate and reap the parser child."""
    try:
        payload = sql.encode("utf-8") if type(sql) is str else b""
    except UnicodeError:
        raise SQLValidationError("Invalid SQL input.") from None
    if not 1 <= len(payload) <= 16384 or not 0 < timeout <= 2:
        raise SQLValidationError("Invalid SQL input.")
    if not _SLOTS.acquire(blocking=False):
        raise SQLValidationError("Policy capacity unavailable.")
    try:
        env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2]),
               "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        with subprocess.Popen([sys.executable, "-m", "trinity.queries.policy_worker"],
                              env=env, close_fds=True, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
            try:
                output, _ = child.communicate(payload, timeout=timeout)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                raise SQLValidationError("SQL policy timed out.") from None
            if child.returncode != 0 or len(output) > 256 * 1024:
                raise SQLValidationError("SQL policy rejected the input.")
            try:
                result = ValidatedQuery.from_bytes(output)
                if result.original_sql != sql:
                    raise ValueError
                return result
            except ValueError:
                raise SQLValidationError("Invalid SQL policy result.") from None
    except OSError:
        raise SQLValidationError("SQL policy unavailable.") from None
    finally:
        _SLOTS.release()
