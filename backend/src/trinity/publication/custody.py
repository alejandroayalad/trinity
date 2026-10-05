"""Prove same-host stop using the original retained lock, never a replacement."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import socket
import stat


class CustodyError(Exception):
    """Carry a fixed safe refusal reason without exposing filesystem paths."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def check_access(root, run):
    """Require the trusted host and private OS-owned root, even for inspection."""
    if (run['worker_execution_ref'] or {}).get('host') != socket.gethostname():
        raise CustodyError('wrong_host')
    try:
        descriptor = os.open(Path(root),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise CustodyError('access_denied')
        finally:
            os.close(descriptor)
    except OSError:
        raise CustodyError('access_denied') from None


@contextmanager
def custody(root, run):
    """Hold the original inode exclusively until the caller's SQL completes.

    The private root and lock must belong to this worker OS account. Open both
    without following symlinks. Missing files cannot be recreated by recovery.
    Nonblocking flock rejects a live preparation child or publication thread.
    """
    ref = run['worker_execution_ref'] or {}
    if ref.get('host') != socket.gethostname():
        raise CustodyError('wrong_host')
    directory = descriptor = None
    try:
        directory = os.open(Path(root),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise CustodyError('access_denied')
        descriptor = os.open(f"{run['id']}.lock",os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise CustodyError('access_denied')
        if info.st_ino != ref.get('lock_inode'):
            raise CustodyError('lock_replaced')
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise CustodyError('lock_held') from None
        yield
    except PermissionError:
        raise CustodyError('access_denied') from None
    except OSError:
        raise CustodyError('lock_unknown') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)
