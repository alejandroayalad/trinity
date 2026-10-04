"""Reconstruct retained receipts and invoke Trinity's existing read-only verifier.

Run in a fresh backend environment with trusted S3 settings. Supply the local
candidate directory. This evidence harness performs no EIA fetch or S3 write.
"""

from dataclasses import fields
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from trinity.adapters.s3 import S3Storage, StoredArtifact
from trinity.config import load_s3_settings
from trinity.connector.pipeline import StoredCandidate, verify_stored_candidate
from trinity.connector.validate import CheckResult, ValidationReport
from trinity.contracts.manifest import canonical_json, read_manifest, sha256


class ReadOnlyClient:
    """Expose only exact-key GET operations to the existing storage verifier."""

    def __init__(self, client, bucket, keys):
        self._client = client
        self.bucket = bucket
        self.keys = keys
        self.calls = []

    def get_object(self, *, Bucket, Key):
        """Reject reads outside the retained bundle inventory and count requests."""
        if Bucket != self.bucket or Key not in self.keys:
            raise ValueError("unexpected_read_target")
        self.calls.append(Key)
        return self._client.get_object(Bucket=Bucket, Key=Key)


def check_result(saved):
    """Restore a result with its original canonical detail bytes."""
    values = {field.name: saved[field.name] for field in fields(CheckResult)
              if field.name != "details_json"}
    values["details_json"] = canonical_json(saved["details"])
    if sha256(values["details_json"]) != saved["details_sha256"]:
        raise ValueError("detail_checksum")
    return CheckResult(**values)


def main():
    """Verify all retained identities and remote bytes without publishing."""
    os.environ.pop("EIA_API_KEY", None)
    root = Path(sys.argv[1]).resolve()
    parent = json.loads((root / "evidence/preparation/result.json").read_bytes())
    if parent["status"] != "stored_unpublished" or parent["published"] is not False:
        raise ValueError("parent_result")
    manifest = read_manifest((root / "manifest.json").read_bytes(), parent["manifest_sha256"])
    attempt = root / "evidence" / parent["attempt_id"]
    validation_bytes = (attempt / "validation.json").read_bytes()
    diagnostic_bytes = (attempt / "diagnostics.json").read_bytes()
    validation = json.loads(validation_bytes)
    diagnostics = json.loads(diagnostic_bytes)
    report = ValidationReport(
        root, manifest, parent["attempt_id"],
        tuple(check_result(item) for item in validation["results"]),
        tuple(check_result(item) for item in diagnostics["evaluations"]),
        validation["status"], diagnostics["warning_digest"], diagnostics["warning_count"],
        diagnostics["approval_required"], sha256(validation_bytes), sha256(diagnostic_bytes),
    )
    bundle = json.loads((root / "bundle.json").read_bytes())
    artifacts = tuple(StoredArtifact(**item) for item in bundle["artifacts"])
    receipt = StoredCandidate(
        root, parent["version_id"], parent["attempt_id"], parent["manifest_sha256"],
        parent["bundle_sha256"], artifacts, parent["storage_evidence_path"],
        parent["warning_digest"], parent["warning_count"], parent["approval_required"],
        published=False,
    )
    settings = load_s3_settings()
    storage = S3Storage(settings)
    prefix = f"{settings.prefix}/{parent['version_id']}/"
    expected = {prefix + item.storage_path for item in artifacts} | {prefix + "bundle.json"}
    readonly = ReadOnlyClient(storage.client, settings.bucket, expected)
    storage.client = readonly
    verify_stored_candidate(report, receipt, storage)
    if set(readonly.calls) != expected:
        raise ValueError("readback_inventory")
    print(json.dumps({
        "status": "verified", "version_id": parent["version_id"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": parent["manifest_sha256"], "bundle_sha256": parent["bundle_sha256"],
        "unique_objects_read": len(expected), "get_requests": len(readonly.calls),
        "s3_write_requests": 0, "eia_requests": 0, "published": False,
        "warning_count": parent["warning_count"], "approval_required": parent["approval_required"],
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
