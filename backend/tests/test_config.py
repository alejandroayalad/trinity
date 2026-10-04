"""Environment and secret-handling checks using synthetic credentials only."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from trinity.config import ConfigurationError, load_eia_settings
from trinity.main import create_app


class EIASettingsTests(unittest.TestCase):
    def test_reads_environment_and_masks_output(self) -> None:
        key = "synthetic-test-key"
        # clear=True isolates the loader from the host environment. patch.dict
        # restores that environment after the block, including on assertion failure.
        with patch.dict(os.environ, {"EIA_API_KEY": key}, clear=True):
            settings = load_eia_settings()
        self.assertEqual(settings.eia_api_key.get_secret_value(), key)
        for output in (str(settings), repr(settings), settings.model_dump_json()):
            self.assertNotIn(key, output)

    def test_rejects_missing_or_blank_key(self) -> None:
        # Tabs and newlines are nonempty strings, but they are still blank credentials.
        for value in (None, "", "   ", "\t\n"):
            environment = {} if value is None else {"EIA_API_KEY": value}
            with self.subTest(value=value):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(ConfigurationError, "Set EIA_API_KEY"):
                        load_eia_settings()

    def test_uses_current_environment_without_a_cached_key(self) -> None:
        # Two loads in one process expose accidental caching of an old credential.
        with patch.dict(os.environ, {"EIA_API_KEY": "first-test-key"}, clear=True):
            first = load_eia_settings()
            os.environ["EIA_API_KEY"] = "second-test-key"
            second = load_eia_settings()
        self.assertEqual(first.eia_api_key.get_secret_value(), "first-test-key")
        self.assertEqual(second.eia_api_key.get_secret_value(), "second-test-key")

    def test_health_does_not_require_eia_credentials(self) -> None:
        # TestClient calls the ASGI app in process. No HTTP server or EIA key is needed.
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(create_app()) as client:
                response = client.get("/health")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
