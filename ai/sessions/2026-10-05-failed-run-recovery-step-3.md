# Failed-run recovery Step 3: atomic command service and HTTP integration

Date: 2026-10-05
Branch: `pending-endpoints-frontend`; base `7d6199b` with Step 2 and design drafts already uncommitted.

## Objective and authorization

[ME] Explained that lease expiry does not prove the old worker stopped and that `execution_fence` rejects obsolete-generation writes. [YOU] clarified that the database fence alone does not stop file/S3 writers; confirmed termination evidence remains necessary. The user then explicitly said “proceed” for Step 3. This is observed understanding of the lease/fence distinction, not a claim of user verification of implementation.

[YOU] implemented the bounded Step 3. Step 4 disposable runtime acceptance, retained recovery, builds, commits, pushes and deployment were not performed. Existing uncommitted Step 2/design work was preserved. The active schedule-settings sibling was inspected read-only and remains separate.

## Input, flow and output

An Admin supplies failed run A, a UUID command key and A's ETag. `RecoveryService.command` authorizes, parses, locks shared admission, locks/rechecks current authority and checks receipt replay. New intent locks current settings for rerun and then target lifecycle rows. It compares the revision and shared stopped-state eligibility before coordinating abandonment and a receipt. Rerun also inserts linked run B and its outbox in this transaction using current settings revision and the current approved policy. The old policy and failure history remain unchanged.

Warning deletion returns a 200 receipt tracking A and creates no run/outbox. New rerun returns 202 with B's tracking URL; a matching authorized replay returns the original receipt identity with 200 before stale revision checks. Commit failures must propagate instead of returning acceptance.

Failure case: B's outbox insert fails after resolving A's warning and discarding A's candidate inside the transaction. The intended PostgreSQL effect is rollback of every change, leaving A's warning unresolved, candidate unchanged, slot retained and no B. Service error propagation passed offline tests; actual PostgreSQL rollback is authored but unexecuted in this step.

## Implemented scope and evidence

| Area | Change and source evidence |
|---|---|
| Service | `RecoveryService.command` in `backend/src/trinity/refresh/recovery.py` owns one `Database.transaction`. It binds replay to current actor/action/old target/fingerprint, freezes current settings for new rerun and returns only after context exit. |
| Persistence | `lock_recovery_target`, `abandon_failed`, `record_warning_resolution`, `accept_run` and `_insert_run` in `backend/src/trinity/refresh/repository.py` keep all effects on the supplied connection. Manual defaults remain; rerun stores its old target separately from its new tracking run. |
| Fences/history | Abandonment records warning resolution and candidate discard actor/time, preserves old terminal failure time and evidence, increments execution/dispatch generations, clears obsolete leases and releases only the old slot. Dispatching rows become pending together with lease clearing to satisfy existing DDL. Terminal run/discarded candidate checks still reject stale delivery. |
| HTTP | `rerun` and `delete_warning` in `backend/src/trinity/refresh/router.py` use the existing RefreshService injection, canonical parameters/request shape, Location and 202 polling headers. SafeTransport permits semantic query validation through those exact method/path pairs after authorization. Route inventory was updated. No main.py injection change was needed. |
| Lock order | `PublicationCommands.command` now authorizes without locks, acquires control, then locks/rechecks identity before receipt lookup. This matches Start and recovery. Its existing replay behavior is preserved. Runtime deadlock proof remains pending. |
| Projections | `read_context` evaluates the shared recovery helper in the read transaction; `admin_context` projects its flags. Production `/me`, history and detail assembly agree in fixture tests, including disabled unsafe state, setup gating for rerun and historical-run isolation. |

The admission refactor follows the `POLICY`/`_insert_run` shape inspected in the active schedule work, adding an optional rerun predecessor. No uncommitted schedule implementation was copied or modified. Future integration must preserve its scheduled occurrence identity and recheck the merged helper. No migration or production dependency was added.

## Tests and verification boundaries

| Check | Actual result |
|---|---|
| Focused recovery/service/HTTP/projection/health | 49 passed, zero skips/failures/errors; 1.876 seconds. Includes 29 Step 2 tests and 18 new Step 3 service/projection tests plus 2 health tests. |
| Affected Refresh/Publication/auth/health suites | 199 discovered: 79 passed, 120 opt-in skips, zero failures/errors; 11.491 seconds. |
| Full offline regression | 662 discovered: 462 passed, 200 opt-in skips, zero failures/errors; 51.757 seconds. Counts overlap the focused suites and must not be added. |
| New PostgreSQL cases | Six authored and added to existing `run_local_sql_checks.py --refresh` discovery. All six skipped in offline runs; none executed. |
| Final static/document review | All 12 changed/new Python files parse; 42 local links/anchors and fences/whitespace in eight recovery documents pass. `git diff --check` passed and the scoped source/test diff was reviewed. |

The six opt-in cases cover current-revision rerun linkage/history, no-work deletion, failure after every actual write for both commands, a deferred receipt trigger failing at COMMIT, and stale outbox lease/generation behavior. They reuse the disposable PostgreSQL fixture and real production SQL. Their synthetic failure fixture starts no child and is not runtime stop proof. Real process/queue races remain Step 4 work.

The tests run with the existing sibling interpreter, selected through its resolved filesystem path, and PYTHONPATH explicitly pointed to this branch's source/tests. Opt-in `TRINITY_TEST_*` values were removed from each broader test subprocess so no retained database or queue was selected. The full command is `python -m unittest discover -s tests -q` from `backend/`; affected tests use sorted module names matching `test_refresh*.py`, `test_publication*.py`, `test_auth*.py`, and `test_health.py`. No dependency installation or build occurred. Existing Starlette/httpx deprecation and sanitized pool messages remain.

One initial new OpenAPI test treated referenced canonical parameters as inline values and failed with KeyError. The test now resolves those references before comparing parameter meaning; the corrected focused and full suites passed. An initial local edit command used a repository-relative path from the backend directory and failed before writing; it was corrected through the exact file path. No production behavior was weakened for either tooling correction.

## Handoff

Done: Step 3 source implementation, route/projection integration and offline verification. Pending: human failure-case explanation, Step 4 real database/HTTP/queue/process acceptance and eventual schedule-branch integration. Blocker: none for the completed offline slice. No SQL runtime, publication, retained operator result, commit or push is claimed.

Next: [ME] explain what must remain unchanged if inserting the new run's outbox fails.

## Subsequent delivery and runtime authorization

[ME] Requested committing/pushing Step 3 and proceeding with Step 4. [YOU] reviewed the clean remote baseline and scoped implementation/test diff; delivery uses one source/test commit followed by one design/evidence commit, preserving history. This supersedes the earlier no-Git/no-Step-4 boundary for these actions. The requested failure-case explanation remains unobserved and is not a blocker after this explicit continuation authorization. Retained deployment and operator acceptance remain separate.
