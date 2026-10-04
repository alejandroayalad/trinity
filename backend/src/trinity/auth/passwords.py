"""Verify full-cost scrypt in bounded, disposable processes."""

import base64
import hashlib
import multiprocessing
import secrets
from threading import BoundedSemaphore

from trinity.errors import Problem

_PREFIX = "scrypt-v1$131072$8$1$"
_SLOTS = BoundedSemaphore(2)


def hash_password(password: str) -> str:
    """Encode a salted password without reducing or truncating its input."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=131072, r=8, p=1,
                            dklen=64, maxmem=256 * 1024 * 1024)
    return _PREFIX + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def _verify(password: str, encoded: str) -> bool:
    try:
        if not encoded.startswith(_PREFIX):
            return False
        salt_text, digest_text = encoded[len(_PREFIX):].split("$")
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
        if len(salt) != 16 or len(expected) != 64:
            return False
    except (ValueError, TypeError):
        return False
    observed = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=131072, r=8, p=1,
                              dklen=64, maxmem=256 * 1024 * 1024)
    return secrets.compare_digest(observed, expected)


def _worker(channel, password, encoded):
    try:
        channel.send((True, _verify(password, encoded)))
    except Exception:
        channel.send((False, False))
    finally:
        channel.close()


def verify_password(password: str, encoded: str, deadline) -> bool:
    """Stop and reap password work before releasing its concurrency slot."""
    if not _SLOTS.acquire(blocking=False):
        raise Problem(429, "rate_limited", retry_after=1)
    process = None
    reader = writer = None
    try:
        ctx = multiprocessing.get_context("spawn")
        reader, writer = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_worker, args=(writer, password, encoded))
        process.start()
        writer.close()
        if not reader.poll(deadline.remaining()):
            raise Problem(503, "auth_unavailable")
        available, valid = reader.recv()
        process.join(timeout=min(1, deadline.remaining()))
        if process.is_alive() or not available:
            raise Problem(503, "auth_unavailable")
        deadline.remaining()
        return valid
    except Problem:
        raise
    except Exception:
        raise Problem(503, "auth_unavailable") from None
    finally:
        if process is not None and process.pid:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        if reader is not None:
            reader.close()
        if writer is not None:
            writer.close()
        _SLOTS.release()
