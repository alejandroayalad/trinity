"""Run auth, catalog and settings acceptance in an isolated, disposable PostgreSQL cluster.

Use PostgreSQL 17.11 binaries via TRINITY_PG_BIN. The cluster listens only on
its private Unix socket; no existing database or service is modified.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from urllib.parse import quote
import unittest


def main():
    """Create a temporary cluster, run checks and always stop our own server."""
    binary = Path(os.environ.get("TRINITY_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin"))
    version = subprocess.check_output([str(binary / "postgres"), "--version"], text=True).strip()
    if version.split()[:3] != ["postgres", "(PostgreSQL)", "17.11"]:
        raise RuntimeError("These checks require PostgreSQL 17.11.")
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="trinity-auth-", dir="/tmp") as temp:
        root = Path(temp)
        data, socket = root / "data", root / "socket"
        socket.mkdir(mode=0o700)
        subprocess.run([str(binary / "initdb"), "-D", str(data), "--username=trinity_test_owner",
                        "--auth-local=trust", "--auth-host=reject", "--no-locale", "--encoding=UTF8"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        # Paths have no whitespace: pg_ctl passes this option string to postgres.
        options = f"-h '' -k {socket} -c unix_socket_permissions=0700 -c timezone=UTC"
        started = False
        try:
            subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "-l", str(root / "postgres.log"),
                            "-o", options, "-w", "start"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, check=True)
            started = True
            subprocess.run([str(binary / "createdb"), "-h", str(socket), "-U", "trinity_test_owner",
                            "trinity_test_auth"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.environ["TRINITY_TEST_DATABASE_URL"] = (
                "postgresql://trinity_test_owner@/trinity_test_auth?host=" + quote(str(socket), safe=""))
            suite = unittest.TestSuite([
                unittest.defaultTestLoader.discover(str(backend / "tests"), pattern=pattern)
                for pattern in ("test_auth*.py", "test_catalog*.py", "test_settings*.py")
            ])
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            print(f"Database acceptance runtime: {version}; disposable Unix-socket cluster.")
            return 0 if result.wasSuccessful() else 1
        finally:
            os.environ.pop("TRINITY_TEST_DATABASE_URL", None)
            if started:
                subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


if __name__ == "__main__":
    raise SystemExit(main())
