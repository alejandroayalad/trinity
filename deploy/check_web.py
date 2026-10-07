"""Check Caddy's real HTTP routing with disposable containers and synthetic data.

Run from the repository root with Docker access: python3 deploy/check_web.py.
The check does not build the frontend or contact PostgreSQL, EIA or S3. It uses
unique container/network names and removes only resources created by this run.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = "caddy:2.11.7-alpine"
API_IMAGE = "python:3.14.8-slim-bookworm"
API_SERVER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.reply()
    def do_POST(self):
        self.reply()
    def reply(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        data = json.dumps({'method': self.command, 'path': self.path,
            'authorization': self.headers.get('Authorization'),
            'body': body.decode()}).encode()
        self.send_response(404 if self.path == '/api/v1/missing' else 200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""


def docker(*args):
    """Run one Docker operation and return output; fail on an unexpected exit."""
    return subprocess.check_output(["docker", *args], text=True).strip()


class WebRoutingChecks(unittest.TestCase):
    """Verify API boundaries and SPA navigation against the deployed Caddyfile."""

    @classmethod
    def setUpClass(cls):
        cls.network = "trinity-web-check-" + uuid4().hex[:12]
        cls.api = cls.network + "-api"
        cls.web = cls.network + "-web"
        cls.files = tempfile.TemporaryDirectory(prefix="trinity-web-check-")
        cls.addClassCleanup(cls.cleanup)
        site = Path(cls.files.name)
        (site / "assets").mkdir()
        (site / "index.html").write_text("<html>synthetic-spa</html>")
        (site / "assets/app-test.js").write_text("console.log('synthetic-asset')")
        docker("network", "create", cls.network)
        docker("run", "-d", "--name", cls.api, "--network", cls.network,
               "--network-alias", "api", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "--entrypoint",
               "python", API_IMAGE, "-u", "-c", API_SERVER)
        docker("run", "-d", "--name", cls.web, "--network", cls.network,
               "--read-only", "--cap-drop", "ALL", "--cap-add", "NET_BIND_SERVICE",
               "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp",
               "--tmpfs", "/data", "--tmpfs", "/config", "-e",
               "TRINITY_SITE_ADDRESS=http://:80", "-p", "127.0.0.1::80",
               "--mount", f"type=bind,src={site},dst=/srv,readonly",
               "--mount", f"type=bind,src={ROOT / 'frontend/Caddyfile'},dst=/etc/caddy/Caddyfile,readonly",
               CADDY_IMAGE)
        cls.url = "http://" + docker("port", cls.web, "80/tcp")
        # Wait for both HTTP listeners, not just a running container status.
        for _ in range(100):
            try:
                with urlopen(cls.url + "/api/v1/me", timeout=1) as reply:
                    if reply.status == 200:
                        return
            except (URLError, ConnectionError, TimeoutError):
                time.sleep(0.1)
        raise RuntimeError("Disposable Caddy/API did not become ready.")

    @classmethod
    def cleanup(cls):
        """Remove this check's resources, including after a failed startup."""
        for name in (cls.web, cls.api):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", cls.network], capture_output=True)
        cls.files.cleanup()

    def test_spa_direct_navigation(self):
        with urlopen(self.url + "/dashboard?range=30d", timeout=3) as reply:
            self.assertEqual(reply.status, 200)
            self.assertIn(b"synthetic-spa", reply.read())
            self.assertEqual(reply.headers["Cache-Control"], "no-store")

    def test_asset_caching_and_missing_asset(self):
        with urlopen(self.url + "/assets/app-test.js", timeout=3) as reply:
            self.assertIn("immutable", reply.headers["Cache-Control"])
            self.assertIn(b"synthetic-asset", reply.read())
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/assets/missing.js", timeout=3)
        self.assertEqual(error.exception.code, 404)

    def test_api_method_path_query_body_and_bearer(self):
        request = Request(self.url + "/api/v1/queries?check=1", data=b'{"sql":"SELECT 1"}',
                          headers={"Authorization": "Bearer synthetic-proxy-check",
                                   "Content-Type": "application/json"})
        with urlopen(request, timeout=3) as reply:
            self.assertEqual(reply.headers["Cache-Control"], "no-store")
            self.assertEqual(json.load(reply), {
                "method": "POST", "path": "/api/v1/queries?check=1",
                "authorization": "Bearer synthetic-proxy-check",
                "body": '{"sql":"SELECT 1"}',
            })

    def test_api_error_is_not_spa_html(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/v1/missing", timeout=3)
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(json.load(error.exception)["path"], "/api/v1/missing")

    def test_z_unavailable_api_is_not_spa_html(self):
        # Stop only the fake upstream. Run this last so other checks retain it.
        docker("stop", "--time", "1", self.api)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/v1/me", timeout=3)
        self.assertEqual(error.exception.code, 502)
        self.assertNotIn(b"synthetic-spa", error.exception.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
