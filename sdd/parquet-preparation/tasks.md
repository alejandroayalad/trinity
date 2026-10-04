# Tasks: typed Parquet candidate preparation

Date: 2026-10-03
Basis: [specification](spec.md) and the five steps in [design](design.md).
Current authorization, October 4: the user requested committing and pushing Step 5 and closing the session with `ai/sessions/` and `NOTES.md`. Alayala will configure S3. This supersedes the earlier session-note exclusion. No live EIA/S3 calls or application publication are authorized by this close.

Maintain data evidence — ongoing. Preserve actual source evidence; synthetic tests are not new anomaly findings.

## Step 1 — Schemas and exact parsing

- [x] Define the three Arrow schemas, analytical names and daily keys in `contracts/datasets.py`.
- [x] Add pure `normalize_row` in `connector/normalize.py`: exact dates/identifiers/decimal text, units and nullable fields; preserve source evidence unchanged on success/failure.
- [x] Retain trailing zeros in returned Decimal values without context rounding; verify exact in-memory Arrow conversion and reject overflow/nonzero excess scale.
- [x] Run focused offline schema/parser checks and relevant existing regressions; record results below.
- [ ] Human reviews the Step 1 diff. Historical review checkbox; the current request explicitly authorizes Step 2 without asserting that this review was recorded.

Coverage: parsing portions of S02–S08 and source-preservation/error boundaries from S31. In-memory Arrow checks do not satisfy S01's saved-Parquet round trip, S05's later warning evaluation or S08's full V02 evidence evaluation. D01/D02 codes are row observations only; D03–D09 and complete diagnostics are Step 3.

## Step 2 — Freeze files

- [x] Write/reopen temporary Parquet for all three datasets without deduplication; complete S01 and remaining round-trip checks.
- [x] Implement canonical schema/manifest identities, new-version reservation and safe file paths; test S18–S21/S24.
- [x] Bind original sanitized evidence and preserve exact numeric values through saved-file conversion.
- [x] Human accepts and closes Step 2, and explicitly authorizes Step 3.

Gate passed: the user requested closing Step 2 and continuing with Step 3.

## Step 3 — Validate saved files

- [x] Implement V01–V08 and the exact 16-result attempt registry; test S09–S17/S22–S25's local boundary, including the shared missing-day rejection.
- [x] Implement D01–D09 and frozen diagnostic identity; test S26–S30. D06 is not applicable when source percentage is absent or capacity is zero, while evaluation still completes and D02 remains applicable.
- [x] Durably retain available failed/error validation and diagnostic evidence as produced; exercise persistence failure/cancellation from S36. Partial evidence never establishes readiness.
- [x] User authorizes committing and pushing Step 3, and proceeding to Step 4.

Gate passed by the user's request to commit, push and start Step 4. No publication side effects.

## Step 4 — Store immutable artifacts

- [x] Implement conditional writes, collision handling, readback SHA-256 and final bundle verification through the trusted adapter.
- [x] Test S25/S34–S35 with injected storage behavior, including ambiguous writes and incomplete prefixes.
- [ ] Verify actual configured storage protection separately before claiming real immutability.
- [x] User authorizes committing and pushing Step 4, and continuing with Step 5.

Gate: successful exact-file validation; real writes require authorization and configured storage.

## Step 5 — Connect the preparation command

- [x] Connect existing extraction to the approved stages, durable journals, bounded execution and truthful exits/output.
- [x] Test offline S31–S38 boundaries, failed-evidence retention and existing extraction regressions; warning-bearing storage success remains unpublished.
- [x] Run the relevant full offline suite and document implemented setup/commands; record live EIA/S3 checks separately.
- [x] User authorizes committing/pushing Step 5 and closing this implementation session. This records delivery authorization, not an observed code walkthrough or live acceptance.

Gate: prior stages verified. Active publication, application-state integration and unrelated product features remain outside this slice.

## Step 1 verification and review handoff

Publication boundary: these documents are committed separately. Step 1 source/tests remain local and uncommitted for human review; the results below describe that local working tree, not the documentation-only checkout.

Runtime: existing `backend/.venv`, CPython 3.14.8 and PyArrow 25.0.1. `uv` was unavailable on this shell's PATH; use the existing environment directly, with no dependency or lockfile changes.

From `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -p test_normalize.py -v
.venv/bin/python -m unittest discover -s tests -v
```

Focused result: **17 tests passed**. Full offline suite: **76 tests passed**, including the 59 existing regressions. The existing Starlette/HTTPX deprecation warning remains; no dependency change was made. No live calls, Parquet file writes, S3 operations or Step 2 implementation. See the [Step 1 evidence](../../ai/sessions/2026-10-03-parquet-schemas-exact-parsing-step-1.md).

Historical next action: [ME] review the new schemas, parser and focused tests before authorizing Step 2. The current request now authorizes Step 2.

## Step 2 verification and review handoff

Base: `5e17656` on `feat/parquet-preparation`. Implementation and this checklist remain uncommitted for review. Use the expanded `CONTRIBUTING.md` from `../trinity-main`; this branch has no copy. No dependency changes or session notes.

`connector/parquet.py::freeze_files` accepts the existing connector's sanitized `RetrievalMetadata` records, fixed date bounds and an existing trusted output directory. It reserves an owner-only UUID directory exclusively, saves `source-evidence.json`, and parses rows from its original response strings. It writes `data/{national,facility,generator}.parquet` without removing duplicates, reopens the bytes, checks exact values, and freezes `manifest.json`. A parsing failure retains source evidence and a safe `failure.json` without a manifest. Failed versions cannot be reused.

`contracts/manifest.py` defines canonical JSON, ordered schema fingerprints, immutable manifest entries and strict manifest reading. `inspect_frozen_files` reopens files against the retained digest and rejects changed evidence, schemas, counts, bounds, checksums, missing/unexpected data, unsafe paths and symlinks. This is the file-integrity primitive for S20; it does **not** emit V08 results or establish readiness. The 16-result attempt registry, source completeness, date coverage, reconciliation and diagnostics remain Step 3. Signed outage values survive; warning evaluation remains pending.

Runtime: existing `backend/.venv`, CPython 3.14.8 and PyArrow 25.0.1. From `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -p test_parquet.py -v
.venv/bin/python -m unittest discover -s tests -v
```

Results: **25 focused tests passed; 101 full offline tests passed**, including all 76 prior tests. Synthetic temporary files cover S01, S18–S21 file behavior, S24, numeric limits under low Decimal precision, original response preservation, concurrent reservations, partial writes and evidence-sync failure. Writer checks confirm Parquet 2.6, Snappy, stored Arrow schema and row groups no larger than 50,000. One initial integration-test fixture used the wrong settings keyword; the corrected fixture uses the existing `EIA_API_KEY` alias. The existing Starlette/HTTPX deprecation warning remains.

Diff reviewed; whitespace checks passed for the checklist and all new files. No formatter, linter or type-checker command is configured in `backend/pyproject.toml`. No live EIA/S3 calls, application-state changes, commits or pushes. Local create-once writes and tamper detection do not prove S3 protection. Command integration, stage deadlines and full readiness validation remain pending in their assigned steps.

Closed by the user's request to continue with Step 3. This closes the review gate without committing the files.

## Step 3 verification and review handoff

Step 2 is accepted and closed. Its three new source/test files are preserved. Step 3 adds `connector/validate.py`, `tests/test_validate.py` and focused backend instructions. All changes remain uncommitted on `feat/parquet-preparation` above `5e17656`. No dependency changes or session notes.

`validate_candidate` reads a retained manifest digest and the exact saved files. It produces the 16-result `trinity-data-v1` registry and 23 dataset-scoped D01–D09 evaluations. Every result binds the version, attempt, manifest, check revision, scope, counts, time and detail identity. V04 compares each dataset to the full requested date set. V06/V07 use integer millionths and record `observed - expected`; absent groups remain absent. D06 uses exact cross multiplication, including equality at the threshold and completed not-applicable evaluations. Source validation uses the connector's full route URLs and recorded key-sort fields without assuming Python's string comparison matches source ID ordering.

Each validation attempt exclusively reserves `evidence/<attempt UUID>/`. It saves check detail JSON and an append-only `journal.jsonl`, flushing and syncing each result before the next check. Attempt-specific `validation.json` and `diagnostics.json` preserve repeated validation without overwriting earlier summaries. Completed failed attempts retain all 16 required outcomes, including errors for unavailable inputs. Interrupted attempts retain prior evidence and an incomplete marker where writable. Warning summaries/digest/count and `approval_required` freeze only after all required checks pass and diagnostics complete.

`verify_validation` checks the passing report against the same attempt's complete journal, summaries, detail files and current candidate files. It rejects mixed diagnostics, incomplete evidence and changed bytes. A failed file recheck retains safe evidence where writable and never replaces the original manifest. This is S25's local handoff guard; actual S3/upload behavior remains Step 4.

From `backend/`, using the existing CPython 3.14.8 / PyArrow 25.0.1 environment:

```bash
.venv/bin/python -m unittest discover -s tests -p test_validate.py -v
.venv/bin/python -m unittest discover -s tests -q
```

Results: **34 focused tests passed; 135 full offline tests passed**, including the 101 prior tests. Coverage includes S09–S17, S20/S22–S23, S25's local guard, S26–S30, and S36's validation-stage persistence/cancellation boundary. Fixtures include 95 advertised versus 55 returned facility rows, shared missing dates, one-millionth mismatches, aggregates beyond DECIMAL(24,6), exact D06 thresholds in both directions, all-ineligible D06 rows, separate attempt identities, summary/journal tampering, write/sync failure and a test child killed after a synced result. The hard-kill test proves incomplete evidence does not establish completion; command supervision/deadlines remain Step 5.

Diff reviewed; whitespace checks passed for tracked changes and both new Step 3 files. The existing Starlette/HTTPX deprecation warning remains. Source/wheel builds and real EIA/S3 checks were not run; no packaging or dependency files changed, and live calls remain excluded. No PostgreSQL/publication changes, commits or pushes. Step 4 remains unstarted.

Delivery update: the user authorized two focused implementation commits and a push, followed by Step 4. The historical uncommitted/no-push statements above describe the original review handoffs. Before delivery, all 135 offline tests passed again.

## Step 4 verification and review handoff

Steps 2–3 were committed as `3330093` (frozen files) and `ba4dd9e` (validation) and pushed to `origin/feat/parquet-preparation`. HEAD and the remote-tracking branch both identify `ba4dd9e`. Step 4 remains local and uncommitted above that revision. No dependency/lockfile changes, live EIA/S3 calls, application-state writes or session notes.

`adapters/s3.py::S3Storage` creates objects with `IfNoneMatch="*"`, streams GET bytes for SHA-256/size verification and closes response bodies on success/failure. Prefix reservation uses a random preparation token. A first reservation conflict stops before data uploads. Ambiguous writes require identical readback; missing bytes permit only bounded conditional retries. Different bytes, permanent errors and unresolved writes fail without replacement. SDK retries are disabled; temporary operations allow three attempts with one/three-second waits inside the 300-second stage budget. Connect/read timeouts are five/ten seconds. Each object is capped at 64 MiB before upload. Checks between operations/chunks do not replace Step 5's hard process supervisor.

`connector/pipeline.py::store_candidate` reuses `verify_validation`, binds the upload snapshot to original validated hashes, and stores all data/manifest/source/validation/detail artifacts. Local `evidence/storage-<token>/` retains the plan, reservation, synced progress and result/failure. Storage execution journals stay local; completed validation journals are uploaded unchanged. It freezes and uploads `bundle.json` last, rechecks every remote member, then verifies saved local evidence before returning a receipt with `published=False`. A warning-bearing candidate retains its review requirement. `verify_stored_candidate` checks the receipt, complete journal, bundle and every remote member; no prefix listing or standalone result marker establishes success.

`config.py::S3Settings` and `load_s3_settings` validate trusted bucket/prefix/region and an optional HTTPS endpoint. Credentials use the existing SDK provider chain; no key is recorded in settings or errors. `.env.example` and backend instructions describe the implemented library boundary. Preparation-command integration, publication and storage provisioning remain excluded.

From `backend/`, using CPython 3.14.8, PyArrow 25.0.1 and boto3/botocore 1.43.108:

```bash
.venv/bin/python -m unittest discover -s tests -p test_s3.py -q
.venv/bin/python -m unittest discover -s tests -q
```

Results: **32 focused storage tests passed; 167 full offline tests passed**, including all 135 prior regressions. Tests use synthetic three-day reconciled Parquet candidates, a conditional in-memory storage double and pinned-SDK `Stubber`. S25/S34–S35 cover changed local files, partial uploads, readback failures/corruption, ambiguous writes including the final bundle, exact byte collisions, concurrent reservations and concurrent complete stores. Additional storage-boundary checks cover warning retention, safe configuration/errors, cancellation, interrupted streams, finite retry/deadline behavior, persistence/sync failure, local evidence corruption and later receipt verification. These do not assert command exits or hard storage-process termination; those remain Step 5.

Diff reviewed; tracked and new-file whitespace checks passed. The existing Starlette/HTTPX deprecation warning remains. No formatter, linter or type checker is configured. Source/wheel builds were not run because packaging and dependencies are unchanged. No real storage protection claim: private access, conditional-write policy enforcement, denied delete/version-delete/policy changes and retained-prefix lifecycle settings need a separately authorized check against configured storage. An alternative endpoint must prove equivalent protection.

Delivery update: the user authorized committing and pushing Step 4, then continuing with Step 5. All 167 offline tests passed again before delivery. Real storage verification remains a separate, unexecuted gate.

## Step 5 verification and review handoff

Step 4 was committed as `1d3c377` and pushed to `origin/feat/parquet-preparation`. Step 5 remains uncommitted above that revision. Existing work is preserved. No dependency/lockfile changes, live EIA/S3 calls, publication writes or session notes.

`connector/prepare.py::main` validates canonical inclusive dates against the UTC date and loads trusted configuration. It exclusively reserves an owner-only version directory before extraction. `supervise` starts a fresh trusted child, durably records stage transitions before acknowledgment, and enforces the designed route/freeze/validation/storage and overall budgets. Timeout or cancellation terminates the child, escalates to kill after five seconds if needed and confirms exit. Missing/early receipts, nonzero exit and failed stages cannot establish success. The parent alone writes the final command result after checking child receipt, saved manifest, bundle and storage completion. Raw child output is suppressed; errors and command output use safe fields.

`connector/pipeline.py::prepare_candidate` reuses `retrieve_all`, the existing reserved-directory freeze operation, `validate_candidate` and `store_candidate`. A new optional route-start callback preserves the extraction command's existing behavior while letting the preparation supervisor time each route. `evidence/retrieval.jsonl` syncs each completed route before normalization. Execution state stays under local `evidence/preparation/`; this changing directory is excluded from uploaded snapshots, alongside storage execution journals. Source, route and validation evidence remains included. Missing SDK credentials now retain a safe configuration code so the command returns `2`; denied access and other runtime failures remain stage failures.

Backend instructions describe the exact module command, working directory, required settings, fixed-window meaning, output layout and exit codes `0/1/2/130`. `.gitignore` excludes the documented `backend/artifacts/` output directory. The command never grants approval or publication. Failed prefixes and existing versions remain untouched.

From `backend/`, using the existing CPython 3.14.8 / PyArrow 25.0.1 / boto3-botocore 1.43.108 environment:

```bash
.venv/bin/python -m trinity.connector.prepare --help
.venv/bin/python -m unittest discover -s tests -p test_prepare.py -v
.venv/bin/python -m unittest discover -s tests -q
```

Results: help exited successfully; **18 focused command tests passed; 185 full offline tests passed**, including all 167 previous regressions. The final full run includes the stage-status gate, execution-journal readback, rejection of replaced intermediate directories and rejection of a valid receipt whose child exits after its deadline. Tests use the October 1–3, 2026 synthetic reconciled fixture with real saved Parquet and real spawned processes. Injected HTTP/storage establishes S31–S35 command behavior: sanitized source echoes, unknown-field retention, warning-free/warning-bearing success, ambiguous write resolution, collisions and storage/readback failures. S36 covers failed validation/diagnostics, route-sink and parent-journal persistence failures, cancellation between stages, actual SIGTERM, blocked validation/storage children that ignore terminate and require kill, a child killed before completion, missing/premature receipts and final-result persistence failure. S37 covers invalid/noncanonical/reversed/future dates, missing configuration/credentials and explicit-window labeling. S38's help, documented command surface and offline regression boundary are verified; live configured execution is not.

Diff and whitespace reviewed, including new command/tests. The existing Starlette/HTTPX deprecation warning remains. No formatter, linter or type checker is configured. A fresh locked install and source/wheel builds were not rerun; package configuration and dependencies did not change. No live preparation, full-window EIA result or deployed S3 policy proof is claimed. Actual private/conditional/no-delete storage protection still requires a separately authorized configured-storage check.

Historical next action: review `main` and `supervise`. The user subsequently authorized delivery and session closure; see the closure record below.


## Session close — October 4, 2026

The user authorized Step 5 commit/push and closure documentation, and will configure S3. Step 5 is committed as `4e6d395`; the separate documentation commit records the handoff. Earlier uncommitted/no-session-note statements above describe their original review stages, not this closure.

Closure reran `.venv/bin/python -m unittest discover -s tests -p test_prepare.py -q` (**18 passed**), `.venv/bin/python -m unittest discover -s tests -q` (**185 passed**) and preparation `--help` (**exit 0**) from `backend/`. Diff/whitespace and closure documentation checks are recorded in the [session close](../../ai/sessions/2026-10-04-parquet-preparation-steps-2-5-close.md). No production code changed after these checks.

Done: Steps 1–5 implemented and offline-tested; delivery and closure authorized.
Pending: alayala's S3 configuration, real protection verification and separately authorized live preparation.
Blocker: no configured-storage/live-pipeline proof; Step 4's real-storage checkbox remains open.

Next: [ME] read `backend/README.md` at “Immutable storage library — Step 4” before configuring S3.
