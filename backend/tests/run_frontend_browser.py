"""Run browser checks against a disposable native PostgreSQL and real HTTP API.

Call only from the disposable cluster runner. Generated persona credentials
travel to the child test process environment, never to output or saved files.
No worker, EIA key, S3, retained database or publication is used here.
"""
import os
import sys
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path
import socket
import subprocess
import threading
import time
import unittest
import uvicorn
from postgres_fixture import PostgresFixture
from trinity.main import create_app


def main():
    """Serve the fixture API until the browser process exits; always close it."""
    class Fixture(PostgresFixture, unittest.TestCase):
        pass
    fixture = Fixture()
    Fixture.setUpClass()
    fixture.setUp()
    resources = ExitStack()
    from test_preview_unit import environment
    resources.enter_context(patch.dict(os.environ, environment()))
    app = create_app(service=fixture.service)
    data_mode = '--frontend-data' in sys.argv
    if data_mode:
        from postgres_fixture import DSN
        from preview_fixture import candidate, publish_fixture
        from preview_runtime_fixture import RuntimeSandbox
        from test_preview_unit import codec
        from trinity.queries.service import PreviewService, QueryService
        fixture.setup_done()
        root = Path(resources.enter_context(TemporaryDirectory()))
        report, receipt, objects = candidate(root / 'candidate')
        _, version = publish_fixture(DSN, report, receipt)
        sandbox = RuntimeSandbox(fixture.database, root / 'stage')
        resources.callback(sandbox.close)
        sandbox.client.add(version, objects)
        resources.enter_context(patch('trinity.queries.config.preview_execution_factory', side_effect=lambda *a, **k: sandbox.execution()))
        app = create_app(service=fixture.service,
                         preview_service=PreviewService(fixture.database, sandbox.execution, codec_factory=codec),
                         query_service=QueryService(fixture.database, sandbox.execution))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                          log_level='critical', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        until = time.monotonic() + 10
        while not server.started and time.monotonic() < until:
            time.sleep(.05)
        if not server.started:
            raise RuntimeError('Disposable HTTP server did not start.')
        env = dict(os.environ, TRINITY_API_TARGET=f'http://127.0.0.1:{port}')
        for role, password in fixture.passwords.items():
            env[f'TRINITY_TEST_{role.upper()}_PASSWORD'] = password
        return subprocess.run(['npm', 'run', 'e2e', '--', 'data.spec.ts' if data_mode else 'session.spec.ts'], cwd=Path(__file__).resolve().parents[2] / 'frontend', env=env).returncode
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        resources.close()
        fixture.tearDown()
        Fixture.tearDownClass()
