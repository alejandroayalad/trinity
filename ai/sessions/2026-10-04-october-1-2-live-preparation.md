# October 1–2 preparation and independent S3 verification

Date: 2026-10-04. Branch: `main`, base `fde733b`, with uncommitted parser/test changes recorded exactly.

## Objective and contributions

[ME] Alayala explicitly authorized a new October 1–2 version, complete validation, conditional S3 upload/readback if validation passed, preservation of both previous runs, exact uncommitted-code attribution, and an unpublished final candidate. This supersedes the original three-day window only for this separate verification run. [YOU] AI ran the existing preparation command, captured the exact tested patch and file hashes, performed fresh-process read-only verification through the existing function, and recorded evidence. No new connector/storage layer or product decision was introduced.

Input → existing three-route extraction → exact Parquet and frozen manifest → all required checks and diagnostics → conditional S3 storage with byte verification → parent-confirmed result → independent readback. A9/A14/A16 remain authoritative: no fabricated dates, waived checks, approval or publication. Failure would retain the new run and stop before dependent work; both previous failures remain intact.

## Results

The [evidence package](../../evidence/live-preparation/2026-10-04-october-1-2/README.md) contains commands, exact code patch, tracked-code file inventory, runtime package versions, receipts, all check summaries, hashes and readback evidence.

Preparation exit 0, version `9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae`, `status=stored_unpublished`, `published=false`. All 16 required checks passed. All 23 diagnostics completed: 22 pass, one informational D09 facility-count mismatch (190 advertised, 110 received), zero review warnings. No source evidence was removed. Counts: 2 national, 110 facility, 190 generator; each route reached an empty terminal page.

Fresh-process `verify_stored_candidate` passed with 50 S3 GETs for all 49 members and the bundle. Byte counts and SHA-256 matched. The evidence harness reconstructed retained dataclasses and provided an exact-key GET-only client interface to the existing adapter; it did not fetch EIA or write S3 objects. The local candidate inventory was identical before/after verification.

The exact tested code diff SHA-256 is `6fcb6e97c0dd51d6dd57ebf169cb40fb4f2e58f7ed82c8ef11c9ff02f1067f92`. The runtime is the existing CPython 3.14.8 environment with locally installed `awscrt==0.36.0`; the lockfile still does not include that optional package. No fresh locked install was performed. Source/test hashes and diff bytes matched after execution. Previous 223-test offline success remains applicable to the unchanged parser/test patch; it was not rerun in this live-only continuation.

Preservation: `4342acf7-776a-41ad-bfdc-d1d471386fb7` retains all seven files unchanged; `33fd735f-8003-42ab-959c-34238e40cd24` retains all 51 files unchanged. Those checks use complete before/after SHA-256 inventories, not only selected files. Credentials were not printed or saved. No cloud policy, publication state, commit or push was changed. No human code-understanding walkthrough is claimed.

## Limits and handoff

This closes live EIA → validated Parquet → verified S3 candidate evidence for October 1–2, with the supplied configuration and tested patch. It does not establish October 3 availability, full-history readiness, permanent protection against future operator policy changes, publication integration or fresh-clone dependency setup. The existing storage-protection record retains the assumption that the supplied writer policy is its only permission policy. Maintain data evidence — ongoing; AN-03 is re-observed and CAND-02 remains separate.

Done: complete two-day live preparation, independent readback, exact code attribution and previous-run preservation.
Pending: human review of the uncommitted correction/evidence and a reproducible CRT dependency decision before fresh-clone verification.
Blocker: none for this bounded unpublished-candidate test.

Next: [ME] review the evidence package and uncommitted parser correction.

## Branch separation verification

Alayala later requested that this live-validation slice move to its own branch while catalog work remains in `feat/catalog-permissions`. AI isolated the parser/tests and live evidence/docs in the sibling `trinity-live-eia-s3-validation` worktree for two focused commits and cherry-pick onto `fix/live-eia-s3-validation`. Shared README/NOTES content was split by subject; catalog decisions, product/API refinements, SDD files and session records are excluded from the live branch.

The isolated source matches the original `tested-code.patch` byte-for-byte. Its full offline suite passed again: 248 discovered, 223 passed, 25 opt-in PostgreSQL checks skipped, in 34.256 seconds. Relative file links and credential checks passed. This is branch-isolation verification, not a repeat of the live cloud run. Historical references to uncommitted code describe the time of that live run and retain the exact tested patch.

Local `.env`, the existing Python environment and ignored `backend/artifacts/` directories remain in the original `trinity` worktree. They are not copied into the new branch. To repeat the evidence harness after this split, use that existing environment and the original retained candidate directory; the evidence report's relative artifact paths refer to that original worktree. No push or PR is part of this branch-separation request.
