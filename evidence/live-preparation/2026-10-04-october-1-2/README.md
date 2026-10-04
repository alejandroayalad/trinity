# October 1–2 live preparation — verified, unpublished

Executed October 4, 2026 against `fde733b` plus the exact uncommitted [code/test patch](tested-code.patch). This verifies only the explicitly requested two-day window. It does not establish October 3 coverage, full-history readiness, application publication or fresh-clone setup.

## Final result

| Evidence | Result |
|---|---|
| Existing preparation command | Exit 0; parent-confirmed `stored_unpublished`, `published=false`. |
| Version | `9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae` |
| Required validation | All 16 results passed. |
| Diagnostics | All 23 completed and frozen; 22 pass, one informational D09 finding. Zero review warnings; `approval_required=false`. |
| Source rows | National 2; facility 110; generator 190. Each route reached an empty terminal page. |
| Independent verification | Fresh process exited 0; 50 exact-key S3 GETs verified all 49 bundle members plus `bundle.json`, with byte counts and SHA-256. No EIA calls or S3 writes. |
| Previous runs | All 7 and 51 files respectively remain byte-identical. The successful candidate also remained unchanged during independent verification. |

D09 preserves the known AN-03 facility mismatch: EIA advertised 190 rows but returned 110 facility rows. Its recorded diagnostic status is `fail` with severity `info`; this is not a failed required check or a review warning. No warning or source value was discarded to obtain success. No publication operation occurred.

## Exact code and environment

- Base commit: `fde733b` (full identity in [tested-source.json](tested-source.json)).
- [tested-code.patch](tested-code.patch): complete `git diff --binary HEAD` for backend source, tests, migrations, dependency definitions/lock and Python version file. Only the decimal parser and its regression tests differ from the base in these scopes. SHA-256: `6fcb6e97c0dd51d6dd57ebf169cb40fb4f2e58f7ed82c8ef11c9ff02f1067f92`.
- [tested-files.json](tested-files.json): SHA-256 inventory of the tracked files in those scopes; no untracked code was present there. Both file hashes and patch bytes still matched after execution.
- [tested-source.json](tested-source.json): Python/package versions, date window and patch/inventory hashes. Existing CPython 3.14.8 environment; optional `awscrt==0.36.0` was installed locally to enable the configured login provider. It remains outside `uv.lock`; no fresh locked installation is claimed.
- The preceding parser-fix checks passed 223 offline tests with 25 PostgreSQL checks skipped. Those tests were not rerun during this live-only continuation; the same source/test contents were recorded and checked unchanged.

The wrapper loaded the EIA key only into the preparation process environment, selected `trinity-writer`, removed static credential overrides and retained sanitized command output. No secret appears in this evidence package. Independent verification did not load `.env` or require an EIA key.

## Evidence locations

- [command-result.json](command-result.json): exit code, safe stdout and empty stderr.
- [preparation-result.json](preparation-result.json): byte-for-byte copy of the parent-written final receipt.
- [verification-summary.json](verification-summary.json): all 16 required results, all 23 diagnostics, retrieval counts/times, original detail paths and hashes.
- [independent-readback.json](independent-readback.json): fresh-process result, exact identities, request counts, candidate preservation and verifier-script hash.
- [manifest.json](manifest.json), [bundle.json](bundle.json): exact retained identities and remote inventory; [prior-runs-before.json](prior-runs-before.json) and [preservation-check.json](preservation-check.json) establish previous-run preservation.

Original local candidate root (ignored by Git):

```text
backend/artifacts/9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae/
```

Relative to that root:

```text
evidence/preparation/result.json
evidence/c8bf1d50-fd02-4f05-80f2-fe67c884a3eb/validation.json
evidence/c8bf1d50-fd02-4f05-80f2-fe67c884a3eb/diagnostics.json
evidence/storage-3ca40d00-8d98-422a-9cf4-9311941b9c30/result.json
```

Remote root:

```text
s3://trinity-alayala-dev-01/private/candidates/9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae/
```

Manifest SHA-256: `01df3875e36a037a4c86ed1dc75536e27a282bcfa2ae1fdfa7e03e87f2ce83dc`.
Bundle SHA-256: `2aa54c906e06994e27e3753062c3df4813d9c44a07b76ccdaf5791b57d58ce0e`.

## Repeat only the independent readback

With the existing local files and environment, run from the repository root:

```bash
env -u EIA_API_KEY -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
  -u AWS_SESSION_TOKEN -u AWS_SECURITY_TOKEN -u TRINITY_S3_ENDPOINT_URL \
  AWS_PROFILE=trinity-writer \
  TRINITY_S3_BUCKET=trinity-alayala-dev-01 \
  TRINITY_S3_PREFIX=private/candidates TRINITY_S3_REGION=us-east-1 \
  backend/.venv/bin/python \
  evidence/live-preparation/2026-10-04-october-1-2/verify_readback.py \
  backend/artifacts/9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae
```

The [evidence harness](verify_readback.py) reconstructs the original report/receipt and calls existing `verify_stored_candidate`. It exposes only allowed exact-key GETs to the adapter. It does not replace the pipeline or implement new storage behavior. Expect exit 0, `status=verified`, and `published=false`; missing or changed local/remote evidence fails verification.

The earlier failed versions remain under `backend/artifacts/4342acf7-776a-41ad-bfdc-d1d471386fb7/` and `backend/artifacts/33fd735f-8003-42ab-959c-34238e40cd24/`. The latter still documents the unavailable October 3 date. Neither was repaired, reused, overwritten or deleted.
