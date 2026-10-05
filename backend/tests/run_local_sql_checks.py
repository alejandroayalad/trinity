"""Run SQL acceptance in an isolated, disposable PostgreSQL cluster.

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
import argparse


def main():
    """Create a temporary cluster, run checks and always stop our own server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Include preview database/HTTP acceptance')
    parser.add_argument('--pattern', help='Select one unittest filename pattern in the disposable database')
    parser.add_argument('--publication', action='store_true', help='Run publication acceptance')
    parser.add_argument('--refresh', action='store_true', help='Run refresh evidence and Preview compatibility acceptance')
    parser.add_argument('--all', action='store_true', help='Include auth/catalog and preview acceptance')
    parser.add_argument('--runtime-only', action='store_true', help='Run only preview container acceptance')
    parser.add_argument('--failfast', action='store_true', help='Stop after the first failure and clean the cluster')
    args = parser.parse_args()
    patterns = ['test_sql_postgres.py']
    if args.preview or args.all:
        patterns.extend(('test_preview_postgres.py', 'test_preview_runtime.py'))
    if args.all:
        patterns.extend(('test_auth_postgres.py', 'test_catalog_postgres.py'))
    if args.runtime_only:
        patterns = ['test_preview_runtime.py']
    if args.refresh:
        patterns = ['test_refresh_postgres.py', 'test_refresh_admission.py', 'test_refresh_dispatch.py', 'test_refresh_worker.py', 'test_refresh_candidates.py', 'test_publication*.py']
    if args.publication:
        patterns = ['test_publication*.py']
    if args.pattern:
        patterns = [args.pattern]
    binary = Path(os.environ.get("TRINITY_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin"))
    version = subprocess.check_output([str(binary / "postgres"), "--version"], text=True).strip()
    if version.split()[:3] != ["postgres", "(PostgreSQL)", "17.11"]:
        raise RuntimeError("These checks require PostgreSQL 17.11.")
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="trinity-sql-", dir="/tmp") as temp:
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
                            "trinity_test_sql"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.environ["TRINITY_TEST_DATABASE_URL"] = (
                "postgresql://trinity_test_owner@/trinity_test_sql?host=" + quote(str(socket), safe=""))
            suite = unittest.TestSuite([
                unittest.defaultTestLoader.discover(str(backend / "tests"), pattern=pattern)
                for pattern in patterns
            ])
            result = unittest.TextTestRunner(verbosity=2, failfast=args.failfast).run(suite)
            print(f"Database acceptance runtime: {version}; disposable Unix-socket cluster.")
            return 0 if result.wasSuccessful() else 1
        finally:
            os.environ.pop("TRINITY_TEST_DATABASE_URL", None)
            if started:
                subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


if __name__ == "__main__":
    raise SystemExit(main())
