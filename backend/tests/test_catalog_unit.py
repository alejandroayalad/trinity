"""Offline catalog HTTP, metadata, denial and operator-check regressions."""

from contextlib import contextmanager, ExitStack
from datetime import date, datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import httpx
import pyarrow as pa
from pydantic import ValidationError

from trinity.auth.check import check_catalog, check_persona
from trinity.auth.permissions import Principal, permitted_dataset_keys, require_dataset
from trinity.catalog.registry import describe_dataset
from trinity.catalog.schemas import CatalogResponse, LastRefresh
from trinity.catalog.service import get_catalog
from trinity.contracts.datasets import DATASETS, DatasetDefinition
from trinity.errors import Problem
from trinity.main import create_app

TOKEN = "x" * 43
HEADERS = {"Authorization": "Bearer " + TOKEN}
NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
OPENAPI = json.loads((Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text())


class MetadataConnection:
    """Provide only the two expected catalog SELECT results."""

    def __init__(self):
        self.publication = {"publication_event_id": None}
        self.refresh = None
        self.calls = []

    def execute(self, statement):
        self.calls.append(statement)
        if "FROM active_publication" in statement:
            row = self.publication
        elif "FROM refresh_runs ORDER BY run_seq DESC LIMIT 1" in statement:
            if "SELECT status, requested_at, finished_at" not in statement:
                raise AssertionError("Unexpected refresh projection")
            row = self.refresh
        else:
            raise AssertionError("Unexpected database operation")
        return SimpleNamespace(fetchone=lambda: row)

    def publish(self):
        self.publication = {
            "publication_event_id": uuid4(), "version_id": uuid4(), "published_at": NOW,
            "coverage_start": date(2026, 10, 1), "coverage_end": date(2026, 10, 2),
            "latest_observation_date": date(2026, 10, 2), "status": "validated",
            "disposition": "active", "run_status": "succeeded",
        }


class CatalogIdentity:
    """Supply controlled identities while keeping the real route and policy."""

    def __init__(self):
        self.role = "viewer"
        self.connection = MetadataConnection()
        self.exit_error = None

    @contextmanager
    def authenticated(self, token):
        if token != TOKEN:
            raise Problem(401, "invalid_session")
        yield Principal("synthetic", self.role, None), self.connection
        if self.exit_error:
            raise self.exit_error


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.identity = CatalogIdentity()
        self.context = TestClient(create_app(service=self.identity))
        self.client = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def get(self, **kwargs):
        return self.client.get("/api/v1/catalog", headers=HEADERS, **kwargs)

    def assert_problem(self, response, status, code):
        self.assertEqual((response.status_code, response.json()["code"]), (status, code))
        self.assertEqual(set(response.json()), set(OPENAPI["components"]["schemas"]["Problem"]["required"]))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-request-id"], response.json()["request_id"])
        UUID(response.json()["request_id"])
        self.assertIsNone(response.json()["blocker"])
        self.assertIsNone(response.json()["current_revision"])
        self.assertTrue(response.headers["content-type"].startswith("application/problem+json"))

    def assert_object(self, obj, schema_name):
        schema = OPENAPI["components"]["schemas"][schema_name]
        self.assertEqual(set(obj), set(schema["required"]))
        self.assertFalse(schema["additionalProperties"])
        for key, value in obj.items():
            rule = schema["properties"][key]
            if "enum" in rule:
                self.assertIn(value, rule["enum"])
            if "maxLength" in rule:
                self.assertLessEqual(len(value), rule["maxLength"])
            if "maxItems" in rule:
                self.assertLessEqual(len(value), rule["maxItems"])

    def test_all_personas_before_and_after_publication(self):
        for published in (False, True):
            if published:
                self.identity.connection.publish()
            for role, keys in (("viewer", ["national_outages"]),
                               ("analyst", ["national_outages", "facility_outages", "generator_outages"]),
                               ("admin", ["national_outages", "facility_outages", "generator_outages"])):
                with self.subTest(published=published, role=role):
                    self.identity.role = role
                    response = self.get()
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual([d["key"] for d in body["datasets"]], keys)
                    self.assertEqual(body["data_ready"], published)
                    self.assert_object(body, "CatalogResponse")
                    self.assert_object(body["freshness"], "Freshness")
                    for dataset in body["datasets"]:
                        self.assert_object(dataset, "Dataset")
                        for column in dataset["columns"]:
                            self.assert_object(column, "Column")
                    self.assertEqual(len(body["metrics"]), 1)
                    self.assert_object(body["metrics"][0], "MetricDefinition")
                    if published:
                        self.assert_object(body["publication"], "Publication")
                        UUID(body["publication"]["publication_event_id"])
                        UUID(body["publication"]["version_id"])
                        self.assertTrue(body["publication"]["published_at"].endswith("Z"))
                        self.assertEqual(body["freshness"]["published_at"], body["publication"]["published_at"])
                        self.assertEqual(body["freshness"]["latest_observation_date"], "2026-10-02")
                    else:
                        self.assertIsNone(body["publication"])
                        self.assertEqual(body["freshness"], {
                            "latest_observation_date": None, "published_at": None, "last_refresh": None})
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    UUID(response.headers["x-request-id"])
                    self.assertEqual(len(self.identity.connection.calls[-2:]), 2)

    def test_metadata_matches_canonical_schema_and_filter_contract(self):
        expected_names = {
            "national": ["period", "capacity", "outage", "percentOutage"],
            "facility": ["period", "facility", "facilityName", "capacity", "outage", "percentOutage"],
            "generator": ["period", "facility", "generator", "facilityName", "capacity", "outage", "percentOutage"],
        }
        units = {"capacity": "MW", "outage": "MW", "percentOutage": "percent"}
        for key, names in expected_names.items():
            definition = describe_dataset(key)
            self.assertEqual([c.name for c in definition.columns], names)
            self.assertEqual(definition.daily_key, list(DATASETS[key].key_fields))
            self.assertEqual(definition.key, DATASETS[key].table_name)
            filters = ["start", "end"] + (["facility"] if key != "national" else [])
            if key == "generator":
                filters.append("generator")
            self.assertEqual(definition.available_filters, filters)
            for column in definition.columns:
                self.assertEqual(column.nullable, DATASETS[key].schema.field(column.name).nullable)
                self.assertEqual(column.unit, units.get(column.name))
                expected_type = "decimal" if column.name in units else "date" if column.name == "period" else "string"
                self.assertEqual(column.type, expected_type)

    def test_metric_has_no_value_or_source_percentage_dependency(self):
        metric = self.get().json()["metrics"][0]
        self.assertEqual(metric["key"], "offline_share_percent")
        self.assertEqual(metric["null_reasons"], ["not_reported", "zero_capacity"])
        self.assertEqual(metric["display_decimal_places"], 2)
        self.assertIn("100 × outage / capacity", metric["formula"])
        self.assertNotIn("percentOutage", metric["formula"])
        self.assertNotIn("value", metric)

    def test_current_role_and_shared_policy_without_response_mutation(self):
        self.identity.role = "analyst"
        self.assertEqual(len(self.get().json()["datasets"]), 3)
        self.identity.role = "viewer"
        result = get_catalog(Principal("test", "viewer", None), self.identity.connection)
        result.datasets[0].columns.clear()
        body = self.get().json()
        self.assertEqual(len(body["datasets"]), 1)
        self.assertEqual(len(body["datasets"][0]["columns"]), 4)
        for role in ("viewer", "analyst", "admin"):
            principal = Principal("test", role, None)
            allowed = permitted_dataset_keys(principal)
            for key in ("national", "facility", "generator", "unknown"):
                if key in allowed:
                    require_dataset(principal, key)
                else:
                    with self.assertRaises(Problem) as caught:
                        require_dataset(principal, key)
                    self.assertEqual(caught.exception.code, "dataset_not_found")

    def test_auth_and_unknown_roles_deny_before_state_reads(self):
        self.assert_problem(self.client.get("/api/v1/catalog"), 401, "authentication_required")
        for token in ("Basic x", "Bearer forged", "Bearer " + "y" * 43):
            response = self.client.get("/api/v1/catalog", headers={"Authorization": token})
            self.assert_problem(response, 401, "invalid_session")
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
        for role in (None, "owner"):
            self.identity.role = role
            self.assert_problem(self.get(), 403, "forbidden")
        self.assertEqual(self.identity.connection.calls, [])

    def test_rejected_parameters_bodies_and_streamed_limit(self):
        for key in ("role", "actor", "dataset", "version", "cursor", "path"):
            self.assert_problem(self.get(params={key: "private-input-canary"}), 422, "invalid_request")
        self.assert_problem(self.client.request("GET", "/api/v1/catalog", headers=HEADERS, content="{}"),
                            422, "invalid_request")
        self.assert_problem(self.client.request("GET", "/api/v1/catalog", headers=HEADERS,
                                              content=b"x" * 65537), 413, "request_too_large")
        self.assertEqual(self.identity.connection.calls, [])

    def test_refresh_all_statuses_preserves_published_readiness(self):
        self.identity.connection.publish()
        for status in OPENAPI["components"]["schemas"]["RunStatus"]["enum"]:
            terminal = status in ("succeeded", "failed", "discarded", "superseded")
            self.identity.connection.refresh = {
                "status": status, "requested_at": NOW, "finished_at": NOW if terminal else None}
            body = self.get().json()
            self.assertTrue(body["data_ready"])
            self.assertEqual(set(body["freshness"]["last_refresh"]), {"status", "requested_at", "finished_at"})
            self.assertEqual(body["freshness"]["last_refresh"]["status"], status)
            self.assertEqual(body["freshness"]["latest_observation_date"], "2026-10-02")

    def test_no_publication_does_not_hide_latest_attempt(self):
        self.identity.connection.refresh = {"status": "running", "requested_at": NOW, "finished_at": None}
        body = self.get().json()
        self.assertFalse(body["data_ready"])
        self.assertIsNone(body["publication"])
        self.assertIsNone(body["freshness"]["published_at"])
        self.assertEqual(body["freshness"]["last_refresh"]["status"], "running")

    def test_corrupt_persisted_state_is_dependency_failure(self):
        self.identity.connection.publication = None
        self.assert_problem(self.get(), 503, "dependency_unavailable")
        for field, value in (("version_id", None), ("status", "preparing"), ("disposition", "discarded"),
                             ("published_at", NOW.replace(tzinfo=None)), ("coverage_end", date(2026, 9, 1)),
                             ("run_status", "running")):
            self.identity.connection.publish()
            self.identity.connection.publication[field] = value
            self.assert_problem(self.get(), 503, "dependency_unavailable")
        self.identity.connection.publication = {"publication_event_id": None}
        for row in ({"status": "failed", "requested_at": NOW, "finished_at": None},
                    {"status": "running", "requested_at": NOW.replace(tzinfo=None), "finished_at": None},
                    {"status": "private-state-canary", "requested_at": NOW, "finished_at": None},
                    {"status": "running", "requested_at": NOW, "finished_at": None, "candidate_id": "canary"}):
            self.identity.connection.refresh = row
            self.assert_problem(self.get(), 503, "dependency_unavailable")

    def test_recorded_timezones_are_normalized_to_utc(self):
        self.identity.connection.publish()
        local = NOW.astimezone(timezone(timedelta(hours=-6)))
        self.identity.connection.publication["published_at"] = local
        self.identity.connection.refresh = {"status": "succeeded", "requested_at": local, "finished_at": local}
        body = self.get().json()
        self.assertEqual(body["publication"]["published_at"], "2026-10-04T12:00:00Z")
        self.assertEqual(body["freshness"]["last_refresh"]["finished_at"], "2026-10-04T12:00:00Z")

    def test_static_failures_are_not_empty_catalog_or_dependency_errors(self):
        with patch("trinity.catalog.registry.DATASETS", {}):
            self.assert_problem(self.get(), 500, "internal_error")
        invalid = DatasetDefinition("national_outages", ("period",), pa.schema([pa.field("period", pa.int32())]))
        with patch("trinity.catalog.registry.DATASETS", {"national": invalid}):
            self.assert_problem(self.get(), 500, "internal_error")
        with patch("trinity.catalog.registry.PRESENTATION", {"national": ("x" * 513, "test", ("start",))}):
            self.assert_problem(self.get(), 500, "internal_error")
        self.assertEqual(self.identity.connection.calls, [])

    def test_catalog_and_errors_do_not_expose_private_canaries(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        for error in (ValueError("private-database-canary"), RuntimeError("private-internal-canary")):
            with patch("trinity.catalog.service.read_publication", side_effect=error):
                response = self.get()
            self.assertIn(response.status_code, (500, 503))
            self.assertNotIn(str(error), response.text + stream.getvalue())
        response = self.get()
        for hidden in ("facility", "generator", "candidate", "actor", "manifest", "s3://"):
            self.assertNotIn(hidden, response.text)

    def test_dependency_cleanup_failure_cannot_send_success(self):
        self.identity.exit_error = Problem(503, "dependency_unavailable")
        self.assert_problem(self.get(), 503, "dependency_unavailable")

    def test_catalog_never_calls_external_or_analytical_operations(self):
        with ExitStack() as stack:
            guards = [stack.enter_context(patch(target, side_effect=AssertionError("Forbidden I/O")))
                      for target in ("boto3.client", "pyarrow.parquet.read_table", "datafusion.SessionContext",
                                     "trinity.connector.client.EIAClient.__init__", "subprocess.Popen",
                                     "trinity.refresh.repository.read_context")]
            for role in ("viewer", "analyst", "admin"):
                self.identity.role = role
                self.assertEqual(self.get().status_code, 200)
            for guard in guards:
                guard.assert_not_called()


class OperatorCatalogTests(unittest.TestCase):
    def test_checker_rejects_hidden_fields_wrong_roles_and_inconsistent_readiness(self):
        body = get_catalog(Principal("test", "viewer", None), MetadataConnection()).model_dump(mode="json")
        check_catalog(httpx.Response(200, json=body, headers={"cache-control": "no-store"}), "viewer")
        for change in (lambda b: b.update(candidate_id="private"), lambda b: b.update(data_ready=True),
                       lambda b: b["datasets"].append(describe_dataset("facility").model_dump(mode="json"))):
            changed = json.loads(json.dumps(body))
            change(changed)
            with self.assertRaises((ValueError, ValidationError)):
                check_catalog(httpx.Response(200, json=changed, headers={"cache-control": "no-store"}), "viewer")

    def test_optional_catalog_check_logs_out_even_on_catalog_failure(self):
        for enabled in (False, True):
            calls = []
            def handler(request):
                calls.append(request.url.path)
                if request.url.path.endswith("login"):
                    return httpx.Response(200, json={"access_token": TOKEN})
                if request.url.path.endswith("logout"):
                    return httpx.Response(204)
                if request.url.path.endswith("settings"):
                    return httpx.Response(403)
                if request.url.path.endswith("catalog"):
                    return httpx.Response(500)
                if calls.count("/api/v1/me") == 1:
                    return httpx.Response(200, json={"role": "viewer", "landing_screen": "waiting"})
                return httpx.Response(401)
            with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
                if enabled:
                    with self.assertRaises(ValueError):
                        check_persona(client, "viewer", "synthetic", catalog=True)
                else:
                    self.assertEqual(check_persona(client, "viewer", "synthetic"), "waiting")
            self.assertIn("/api/v1/auth/logout", calls)
            self.assertEqual("/api/v1/catalog" in calls, enabled)
