# Refresh and publication — integration contract

Status: **tasks 2–4 implemented; task 5 integration pending**, October 4, 2026. Contract and implementation status.
Initial draft baseline: `82a4af7`; reconciled implementation baseline: `aea1eda` (merged SQL/Preview); branch: `feat/refresh-publication`.

The user authorized implementation after correcting the Preview field mapping and migration baseline. See [implementation status](tasks.md#implemented-boundary-and-verification).
[A9/A16/A19/A20](../../DECISIONS.md), [canonical schema](../../docs/schema.md),
[API contract](../../docs/api-contract.md), and [backend ownership](../../docs/backend.md)
remain authoritative. Physical additions below are proposals, not accepted decisions.
Implemented additions are reconciled in A22/A23 and the canonical schema; unimplemented details remain proposals.

## 1. Human review

Input: one admitted refresh run and the saved outputs of its preparation process.
Flow: freeze the run's dates → prepare/store one candidate → verify its complete
evidence → register it in PostgreSQL → route it to review or publication.
Output: either a candidate awaiting Admin approval, or durable publication work.
Only the publication transaction makes data visible to analytical requests.

Example: all 16 required results pass, all 23 diagnostics complete, and no review
warnings occur. Registration stores the exact identities and queues publication.
If a generator file then changes, publication fails its integrity check. The old
active publication remains available. A receipt marked `stored_unpublished` is
never a publication event.

Recommendation: retain the existing preparation format. Add a strict, internal
import boundary with durable checksums and an explicit connector-attempt/database-step
mapping. Do not add a public candidate-upload endpoint or infer readiness from a prefix.

## 2. Existing outputs and code evidence

Paths in this table are relative to the candidate root unless stated otherwise.
These are observed source contracts, not new runtime test results.

| Output | Producer and exact contents | Consumer rule |
|---|---|---|
| Final command receipt, `evidence/preparation/result.json` | `prepare.supervise` in `backend/src/trinity/connector/prepare.py` writes only after child exit 0 and `_verify_receipt`. Carries `version_id`, `attempt_id`, `manifest_sha256`, `bundle_sha256`, contract/checkset, requested dates, warning digest/count, approval flag, storage evidence path, artifact count, `window_kind=explicit`, `status=stored_unpublished`, `published=false`. | Retain exact bytes/digest under worker custody. Child `receipt.json` alone is incomplete. No run ID, fence, database step ID, or publication grant exists in this format. |
| Analytical manifest, `manifest.json` | `Manifest` / `read_manifest` in `backend/src/trinity/contracts/manifest.py`: format 1, integer contract 1, version UUID, dates, source-evidence digest, sorted file entries. Entries contain dataset/path/hash/schema fingerprint/size/row count/date bounds. | Verify against the previously retained manifest digest. Exactly the three dataset keys must occur; multiple files per dataset remain allowed. |
| Validation attempt, `evidence/<attempt_id>/validation.json` | `validate_candidate` in `backend/src/trinity/connector/validate.py`: common version/attempt/manifest/window/contract/checkset binding, expected registry, 16 V01–V08 results, status and error code. Each result carries detail path/hash and timestamp. | One complete passing attempt only. Preserve failed/error outcomes too; do not combine attempts. |
| Frozen diagnostics, `evidence/<attempt_id>/diagnostics.json` | Same validator: registry `warnings-v1`, 23 scoped D01–D09 evaluations, summaries, `frozen`, warning digest/count and approval flag. | Require complete known registry and `frozen=true` for eligibility. Diagnostic `fail` means an observed condition; `error` means incomplete. |
| Detail files and `evidence/<attempt_id>/journal.jsonl` | `_Journal` writes exact canonical details and durable results before completion; completion binds the validation/diagnostic file hashes. | Recheck detail bytes, expected results, start/completion bindings, and absence of contradictory failure evidence. |
| `source-evidence.json`, saved sanitized responses and Parquet | `parquet` freezing and validation preserve source evidence and identify exact data bytes. | Source index digest must match manifest; verify referenced evidence and all bundle members. Never reinterpret missing observations as zero. |
| `bundle.json` and remote `reservation.json` | `pipeline.store_candidate` in `backend/src/trinity/connector/pipeline.py` uploads immutable members, then bundle last; bundle includes binding and path/hash/size inventory, including reservation. | Pin bundle digest outside bundle. `artifact_count` counts members, excluding bundle itself. Verify bundle plus every member; do not hardcode the live example's 50-object total. |
| `evidence/storage-<token>/{plan,reservation,result}.json` and journal | `store_candidate` records storage completion locally. `StoredCandidate` returns bundle identity, member inventory, attempt, manifest and warnings. | Preserve local receipt evidence. Storage and preparation execution journals are excluded from the remote frozen bundle; S3 alone cannot reconstruct them. |

`verify_validation` checks local validation/evidence identities.
`verify_stored_candidate` checks original local report/receipt plus remote members.
Neither is currently a general saved-JSON deserializer or a PostgreSQL registration service.
The future loader must construct and validate these typed inputs without computing a new
trusted digest from potentially replaced files. Existing CLI verification is useful but
does not establish database ownership or worker authority.

### Original draft inventory — superseded implementation baseline

- Severity and scope: implementation prerequisite; committed preparation/local-auth boundary.
- Expected: registration can retain all identities and recover durable dispatch.
- Observed: `0002_app_entry.upgrade` creates lifecycle/read dependencies but no artifact, result, outbox, or command-receipt tables. `refresh.repository.read_context` and `publication.repository.read_publication` are reads, not registration/publication writers.
- Evidence: inspected `backend/migrations/versions/` with `rg --files`; actual files are `0001_local_auth.py` and `0002_app_entry.py`. Inspected their `CREATE TABLE` statements and `backend/src/trinity/{refresh,publication}/`. Expected `dataset_artifacts`, `validation_results`, `job_outbox`, `api_commands` DDL and writer methods are absent there. The schema document specifies those tables; it does not create them.
- Failure scenario: wiring the current stored receipt directly to publication has nowhere to persist required results or durable dispatch. A crash after storage cannot establish an approved, registered publication from the active-pointer table alone.
- Recommended correction: add the missing persistence and guarded service boundary described below before enabling commands.
- Validation still required: migrations, rollback, identity rejection, recovery, concurrent publication and real PostgreSQL integration. No such tests ran for this design.

## 3. Map outputs to persistence

Lifecycle columns are in `0002_app_entry.py`; Preview adds `evidence_bundle_sha256` and `validation_attempt_id` in `0004_preview_evidence.py`. The implementation chain is 0001 → 0002 → 0003_query_admission → 0004_preview_evidence → 0005_refresh_evidence → 0006_refresh_dispatch. The original inventory above describes the earlier draft baseline only.
No current database was inspected or changed. Migration files establish source DDL,
not the schema deployed in any particular database.

| Source / application-owned value | Existing target | Proposed addition or conversion |
|---|---|---|
| Trusted run ID, actor, settings snapshot, window, current fence | `refresh_runs.id/requested_by/policy_snapshot/requested_start/requested_end/window_frozen_at/execution_fence`; `refresh_control.holder_run_id` | No receipt field may override these. Reserve candidate ID only after end discovery is frozen. |
| Receipt/manifest `version_id` | `data_versions.id`, unique `run_id` | Worker preallocates ID and exact candidate root; receipt must match. Preserve one version per run. |
| Manifest hash and freeze/registration times | `data_versions.manifest_sha256/manifest_frozen_at/created_at/validated_at` | Times are application events, not invented receipt fields. Use UTC times from durable stage records where present; record acceptance time explicitly. |
| Requested bounds; measured national max period | `data_versions.coverage_start/coverage_end/latest_observation_date` | Coverage equals run window. Require measured coverage under V04; latest observation is measured national max, never wall-clock date. |
| Integer manifest `contract_version=1`; checkset | `data_versions.contract_version/validation_checkset` (text) | Explicit supported map: integer `1` → text `trinity-data-v1`; checkset remains `trinity-data-v1`. Never blindly stringify integer `1` or silently upgrade a stored policy. |
| Manifest entries | No physical table yet | Create canonical `dataset_artifacts`; map entry fields directly plus application UUID `id` and candidate `version_id`. Only analytical files go here. |
| Connector UUID `attempt_id`; database validation execution | Existing `refresh_steps.id/run_id/stage/work_key/attempt/execution_fence`; `data_versions.validation_step_id` | Add nullable `refresh_steps.validation_attempt_id uuid`, globally unique when non-null, allowed only for `stage=validate`. Bind once to this run's validation step. Set `data_versions.validation_attempt_id` to that exact attempt when selecting `validation_step_id`. Connector UUID and database step UUID are distinct. Numeric `attempt` is retry ordinal, not connector UUID. |
| All required/diagnostic result fields | No physical table yet | Create canonical `validation_results`; `step_id` comes from the explicit mapping. Keep `details jsonb`, and add `details_path text`, `details_sha256 text`. Preserve exact bytes in retained evidence; do not hash PostgreSQL JSON rendering. |
| Frozen warning fields | `data_versions.review_warning_digest/review_warning_count/approval_required/diagnostics_frozen_at` | Rename receipt `warning_digest/count` only at the adapter boundary. Complete one passing attempt before filling fields. Keep null on incomplete/failed diagnostics. |
| Bundle/receipt and validation summary identities | Existing Preview evidence pair | Reuse existing `data_versions.evidence_bundle_sha256` and `validation_attempt_id` from `0004_preview_evidence`; add nullable `preparation_receipt_sha256`, `storage_verified_at`; add nullable `refresh_steps.validation_sha256`, `diagnostics_sha256` for validation steps. Store receipt bytes in durable trusted evidence custody addressed by version and receipt hash. Freeze identities after acceptance. |
| API request, accepted action, queue obligation | Existing run `request_key`; no command/outbox tables | Create canonical `api_commands` and `job_outbox` with actor/body binding, unique command keys, lease/dispatch fields and unique `(run_id, job_kind)`. Queue payload contains schema version and IDs/generation, never paths or credentials. |
| Approval and publication outcome | Existing `approvals`, `publication_events`, `active_publication` | Reuse fields; approval binds candidate, manifest, validation step and frozen warning digest. Publication is a unique event plus atomic pointer change. |

The warning digest has a non-obvious existing meaning: `diagnostic_identity` hashes
**all 23 diagnostic summaries**, including informational and zero-occurrence results,
sorted by code/scope with registry and detail hashes. Warning count is the number
of warning code/scope summaries with affected rows, not the number of affected rows.
Keep this format. Zero warnings still has a digest. D09 remains informational.

### Implemented initial migration sequence

1. `0005_refresh_evidence` follows `0004_preview_evidence`: artifact/results tables, receipt/summary identities, unique validation-attempt mapping and guarded selected-step ownership.
2. `0006_refresh_dispatch` adds outbox/command tables and indexes plus worker deadline/ownership columns. Keep existing singleton rows and historical records; do not edit applied migrations.
3. Validate existing rows before stronger constraints. Do not backfill invented checksums or pretend existing `validated` rows have receipts. Legacy rows with missing proof remain publication-ineligible; an existing active pointer must trigger explicit operator review, not silent deletion or reassignment.

Proposed types: UUID record IDs, bigint counts/revisions, date coverage,
timestamptz times, text normalized paths and lowercase 64-hex hashes, jsonb payloads/details.
Use the canonical table field lists and nullability in `docs/schema.md` for new tables.
Require positive file counts/sizes, valid dataset/scope/status/severity values,
`0 <= failed_count <= checked_count`, pass → zero failures, and unique
`(version_id, step_id, check_code, dataset_key)` / `(version_id, storage_path)`.
Complete required passes must also have nonzero checked counts.

Ownership needs more than independent FKs. Proposed deferred constraint triggers check
that result/selected validation steps have `stage=validate` and the version's run;
approval uses that version's selected validation step/manifest/warnings; publication
approval belongs to its version; failure-warning version belongs to its run.
Freeze manifest/artifact/result/receipt bindings once accepted; preserve failed attempts.
Services still enforce full registry completeness, file integrity and legal transitions.
Triggers do not replace verification of external bytes. Test rejected direct SQL writes
as well as service calls. Exact SQL belongs to implementation after this review.

`publication_events.idempotency_key` is already UUID, while A9 names the logical
effect `publish:<version_id>`. Proposed encoding: use `version_id` itself as the UUID
publication idempotency key (one event per version). Keep the logical string for the
outbox deduplication key. Never cast `publish:<uuid>` to UUID.

## 4. Internal handoff and identity checks

The input envelope is trusted worker context: run ID, reserved version ID, execution
fence, validation step ID, frozen policy/window, and retained receipt bytes/hash.
Storage location comes only from trusted configuration plus version ID. An HTTP body
cannot provide an object path, endpoint, bucket, receipt or result set.

1. Confirm live worker ownership and record progress before expensive reads. Require a final parent receipt, canonical encoding, successful status and `published=false`; reject child-only, missing, failed or contradictory completion. Persist its original hash under worker custody before any crash-recovery re-import.
2. Verify manifest against retained hash, supported format/contract, exact version and run dates. Load bundle against retained bundle hash; reject duplicate/unsafe paths, mismatched member sizes/hashes or missing expected data/source/check evidence. Verify remote bundle and every member. Do not trust directory names, S3 ETags or counters as proof.
3. Require the same version, manifest, connector attempt, contract, checkset and window across receipt, bundle, reservation, validation, diagnostics and journals. Check exact required registry (16 unique passing rows) and diagnostic registry (23 complete known evaluations); recompute details and diagnostic identities using existing canonical rules. Unknown/missing/error diagnostics block readiness.
4. Under the current fence, register the mapping, artifacts, all results and frozen identities in one short transaction. Require current slot, run `running`, active candidate, unchanged policy/window and no competing acceptance. Set `validated` only with accepted storage proof. Zero warnings → `publishing` plus publish outbox; warnings → `awaiting_approval`, retaining slot. If any write fails, all readiness and routing effects roll back.
5. Publication verifies the retained evidence and remote bytes again outside the final SQL transaction. Lock/recheck current state, approval, fence/generation, run ordering and nonregressing coverage before the atomic event/pointer/success/release transaction. Immutable storage is required between verification and commit.

The same accepted receipt replay is a no-op only after exact persisted-identity comparison;
a different receipt/attempt/hash cannot replace an accepted binding. A stale worker cannot
perform even an idempotent state mutation. Publication delivery after success returns the
existing event without moving the pointer or rechecking obsolete slot ownership.

### Preparation interfaces and continuation status

- Window discovery (implemented in task 4): the CLI still accepts explicit dates only. Product refresh must discover the newest national observation once, persist it with start `2024-10-02`, and pass those frozen bounds to preparation. The two-day live sample is not eligible evidence for a full-history product run.
- Attempt registration (implemented in task 4): the validator generates its attempt internally and calls a durable start hook before checks. The supervisor persists that attempt-to-step mapping; failed/partial import reads retained journals. Do not fabricate a successful step from a command exit alone.
- Stage naming: map `extract:<dataset>` → `extract` with dataset work key; `freeze` → `prepare/files`; `validation` → `validate/candidate`; `storage` → `prepare/storage`. Storage is prepublication preparation, not a successful `publish` step. Preserve sequential `step_seq` even when a later step uses stage `prepare`.
- Recovery: existing CLI reserves a fresh root and has no resume command. Do not rerun it into an existing root. Retain local evidence on durable worker storage. If the final receipt and original pinned identities survive a crash, recover by verification/import. If they do not, fail closed with retained evidence and Admin recovery; a remote bundle alone is insufficient. Resume of incomplete stages needs a separate bounded worker design and cannot silently create a second version in the same run.
- Budgets: [A23](../../DECISIONS.md#a23--durable-refresh-dispatch-and-one-fenced-preparation-execution) now records the implemented worker/dispatch limits and durable attempt custody. Full-history capacity remains unverified. Preserve A19's three-attempt temporary-external-failure ceiling across redelivery; do not stack retries that multiply it. Permanent validation/integrity failures are never automatically retried.

## 5. Lifecycle, transactions and recovery

This restates the accepted schema lifecycle for the handoff; it introduces no new status.
Run status, version validation status and version disposition are separate fields.

| From → to | Guard and atomic effect | Admission slot |
|---|---|---|
| none → `requested` | Authorized Admin or due schedule; setup complete; lock control; insert run/policy, command receipt where applicable and refresh outbox together. | Reserve. |
| `requested` → `running` | Claim lease, increment execution fence; freeze discovered window before candidate creation/extraction. | Hold. |
| `running` → `awaiting_approval` | Register one stored, validated candidate with complete nonempty warnings. Release worker lease. | Hold. |
| `running` → `publishing` | Same verification with zero warnings; commit publication outbox with transition. | Hold. |
| `awaiting_approval` → `publishing` | Current Admin and candidate revision; exact bound approval + outbox + transition in one transaction. | Hold. |
| `publishing` → `succeeded` | Intact eligible version; current fence/generation; sequence newer than active and coverage start <= active start/end >= active end. Insert unique event, switch pointer, finish run and clear slot together. | Release. |
| `requested/running` → `failed` | Permanent error or exhausted recovery; retain partial artifacts/checks, safe failure warning and terminal finish time. No publication. | Hold until resolution. |
| `publishing` → `publication_failed` | Permanent publication error or retry exhaustion; new unresolved warning. Candidate retains validation evidence; finish time remains null. | Hold. |
| `publication_failed` → `publishing` | Explicit Admin retry only for intact active validated unpublished candidate and recoverable operational failure; original approval remains required. Resolve warning, increment publication generation/fence/revisions and rearm existing outbox. | Hold. |
| `awaiting_approval/publication_failed` → `discarded` | Admin discard, no active publisher; permanently discard candidate, resolve warning if any, invalidate stale work and finish. | Release. |
| `failed/publication_failed` → `failed`, optionally new `requested` | Warning deletion closes blocker; run-again additionally creates new run/version later and refresh outbox. Abandon any candidate; preserve history. New-run failure rolls back old warning resolution too. | Release, or transfer atomically. |
| nonterminal → `superseded` | Newer publication already exists; invalidate stale work and mark candidate superseded; finish run and resolve warning. | Release only if owned. |

Terminal states: `failed`, `succeeded`, `discarded`, `superseded`.
`publication_failed` and `awaiting_approval` require Admin action, not automatic replay.
`failed` can retain the slot through its unresolved warning without becoming nonterminal.
Discard never deletes bytes or audit rows. Newer publication and coverage regression are
separate cases: the former supersedes old work; the latter blocks publication with
`coverage_regression`, and cannot be bypassed by retry or approval.

All competing mutations use the canonical lock order: control → run → candidate →
active publication → warning/command/outbox. External calls stay outside SQL transactions.
Recheck revisions, slot ownership, disposition, generation and fence under locks.
All stage/result writes carry the current execution fence; expired or replaced workers
cannot register outcomes. An unknown live process state cannot justify overlapping writers.

Queue delivery is at least once. Outbox acknowledgment is not job completion.
Recovery inspects durable `requested/running/publishing` work, increments fences when
reclaiming, and repairs unfinished work using dispatch generation. Explicit publication
retry increments publication generation; it does not create a new candidate or approval.
Rerun and publication retry are different operations. Same command key/actor/action/body
returns its stored receipt before stale-revision checks; conflicting reuse fails.
Concurrent recovery actions can produce only one committed outcome.

## 6. Acceptance cases — required before enabling implementation paths

These are review cases, **not tests run in this task**. Use synthetic connector evidence
for boundary tests and disposable PostgreSQL for transaction/concurrency tests.

| ID | Setup/action | Required observation |
|---|---|---|
| IC01 | Complete same-candidate receipt, 16 passes, 23 diagnostics, zero warnings. | All mappings/identities commit; one publish outbox; `publishing`; no event until publisher commits. |
| IC02 | Same evidence with warning summary; then approve as current Admin. | `awaiting_approval` blocks new refresh; approval binds exact identities; one publication obligation. |
| IC03 | D09 informational mismatch only. | Warning count zero; automatic route. Digest still includes D09. |
| IC04 | Required failure, missing result, duplicate pair, or 16 passes assembled from two attempts. | Preserve evidence; no eligible candidate or publish outbox. |
| IC05 | Unknown diagnostic, missing one of 23 evaluations, diagnostic error, changed detail or incorrect digest/count. | Block readiness; never substitute empty warning list. |
| IC06 | Receipt A with manifest, result, reservation or database step from B. | Reject each mismatch, including same-looking values with different attempt/run. No partial acceptance. |
| IC07 | Child receipt without parent completion; partial upload; bundle member absent; invalid path or duplicate member. | No registration success. Prior publication unchanged. |
| IC08 | Alter manifest, data, source evidence, validation, diagnostic, journal or bundle after initial validation. | Hash/binding recheck rejects each variant before publication. |
| IC09 | Inject failure after artifact/results writes but before outbox/commit. | Entire acceptance transaction rolls back; exact receipt can be retried without duplicate rows. |
| IC10 | Replay identical receipt; replay differing receipt for same version; stale worker completes after reclaim. | Exact current-owner replay has no new effects; conflicting/stale writes rejected. |
| IC11 | Crash after stored receipt before registration, and after registration before queue acknowledgment. | Retained identity enables safe import in first case; committed outbox/state recover second. Missing trusted receipt fails closed. |
| IC12 | Crash before enqueue, after enqueue, and Redis loss after delivered acknowledgment. | Durable recovery repairs eligible work; duplicate queue jobs create one publication event. |
| IC13 | Two manual requests, or schedule/manual collision; replay command with changed actor/body. | One lifecycle admitted; matching replay returns receipt; conflicting reuse fails. |
| IC14 | Two approvals; publication retry vs discard; rerun vs delete warning. | One allowed state effect; loser conflicts or receives same-command receipt. No abandoned candidate publishes. |
| IC15 | Recoverable publication failure then explicit retry, for automatic and approved candidates. | Same version/files/approval retained; generation advances; outbox rearmed; new failure creates new warning history. |
| IC16 | Permanent integrity/coverage failure then retry/approval request. | Ineligible; neither action bypasses checks. Warning resolution/rerun remains the recovery path. |
| IC17 | Publish newer run, deliver older work; or newer run has smaller coverage. | Older work superseded; smaller coverage rejected. Active pointer never regresses. |
| IC18 | Fail each statement/commit in final publication; deliver job again after successful commit. | Failure leaves previous pointer and no partial success; postcommit replay returns original event. |
| IC19 | First refresh fails; query spans publication switch. | First case stays unavailable; second uses one pinned retained version throughout. |
| IC20 | Change schedule/policy during review; disable Admin before approval; Viewer submits command. | Frozen policy preserved; current authorization enforced; no unauthorized candidate reads or writes. |
| IC21 | Clean install and upgrade from 0004_preview_evidence with historical/invalid cross-run rows. | Tables/constraints install without evidence deletion; invalid legacy data blocks hardening with explicit report, not fabricated proof. |
| IC22 | Receipt integer contract 1 vs unsupported contract; digest includes informational summaries; storage stage completes. | Supported explicit conversion only; digest unchanged; storage is recorded as preparation, never publication. |
| IC23 | Worker crashes after end discovery; two-day CLI sample offered to full-history run. | Frozen dates reused; sample rejected for run-window mismatch. |
| IC24 | Lost local receipt, exhausted external retry counter or unresolved child termination. | No adoption from S3 prefix alone, no reset retry budget, and no overlapping writer. Retain blocker for recovery. |

## 7. Review gate

Done: corrected Preview bindings, linear migrations and verified registration boundary.
Pending: remaining Refresh tasks and production publication execution.
Blocker: none for the next authorized coding task; runtime evidence is limited to
the checks in [tasks](tasks.md). Worker budgets remain proposed starting values.

## Preview correction acceptance

The writer must populate `data_versions.evidence_bundle_sha256` from receipt
`bundle_sha256` and bind `data_versions.validation_attempt_id` to the selected
validation step. There is no second candidate bundle column. Test registration
through the new writer, synthetic publication in a disposable database, and the
actual `PreviewService` plus frozen-diagnostics reader. Distinguish that compatibility
proof from the later production publisher. Test both a clean installation and
upgrade from 0004 with retained Preview evidence unchanged and one Alembic head.
