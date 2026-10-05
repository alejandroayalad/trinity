# Failed-run recovery Step 2: parsing and eligibility

Date: 2026-10-05
Branch: `pending-endpoints-frontend`; base `7d6199b`.

## Objective and authority

[ME] Accepted the design and requested starting tasks. [YOU] implemented the bounded Step 2 from the existing task list: command parsing, response literals, read-only eligibility, failure-producer tracing and lock-order reconciliation. Step 3 mutation routes remain behind the next gate. No Git commit/push was requested for this implementation turn.

Existing uncommitted design/tasks and documentation changes were preserved. The schedule-settings sibling has active uncommitted implementation; it was inspected read-only and not changed or imported. Maintain data evidence — ongoing; no new source observations were fetched.

## Input, flow and result

`parse_recovery_command` in `backend/src/trinity/refresh/schemas.py` accepts a run ID, recovery action, raw body, key headers and run ETag headers. After future caller authorization, it validates exact syntax and returns immutable `RecoveryCommand` identity/revision. Rerun accepts an empty JSON object; warning DELETE accepts zero bytes only. It does not look up state or replay receipts itself. `ActionReceipt` now accepts the canonical rerun/delete actions and warning_resolved result alongside existing actions.

`recovery_actions` in `backend/src/trinity/refresh/recovery.py` accepts trusted rows from one authorized transaction, checks current admission/warning/candidate linkage, rejects published or inactive candidates and loads stop evidence. It returns two boolean flags, not authorization. No caller exposes these flags yet; command and read-side integration belong to Step 3.

Failure example: a run has an old lease but no confirmed child stop. Both actions remain disabled. A retained owner with a true stop marker and matching owner identity can be safe because `ExecutionService.fail` already checked current owner/fence and persisted terminal failure after child stop. This is source-derived trust in producing writes, not independent runtime proof from a boolean alone.

## Evidence and design reconciliation

Traced all four `fail_run` call sites: dispatch claim/recovery exhaustion, pre-claim policy rejection, and confirmed execution failure. Started failure also rejects running steps and non-rejected candidates; a present reference version must match. Pre-claim failure requires no candidate, step, owner, execution reference or fence increment, plus retained dispatch attempts. Publication failure reuses `publication.checks.stopped_failure` for the current generation. Unknown and contradictory shapes fail closed.

The current schema head is `0007_refresh_registration`; no migration or dependency was added. The [design reconciliation](../../sdd/failed-run-recovery/design.md#step-2-source-reconciliation) records the lock graph, actual JSON proof fields and the outbox lease/status constraint. Step 3 must align candidate command order with control-first Refresh order. No lock order was changed in this step.

Current schedule work has `POLICY`, `_insert_run` and `accept_scheduled_run`; Step 3 must reuse the delivered helpers. Settings update locks user/session then settings without later acquiring control. Scheduler locks control then settings. Those observations apply to the inspected uncommitted sibling snapshot and must be rechecked at integration.

## Checks and actual results

The branch has no `backend/.venv`. Reused the existing sibling CPython environment without installing packages; PYTHONPATH selected this worktree's `backend/src` (its resolved import path was verified). From `backend/`, the interpreter is `../../trinity/backend/.venv/bin/python`; use its resolved path to avoid Python prefix warnings. Backend uses unittest; no separate formatter/linter/type-checker command is configured in its pyproject.

| Check | Result |
|---|---|
| Initial focused `-m unittest discover -s tests -p test_refresh_recovery.py -v` | 28 passed in 0.004 seconds. |
| Affected suite after candidate-identity regression added | 175 discovered, 61 passed, 114 skipped, zero failures/errors; 8.241 seconds. Includes all 29 new recovery tests. |
| Scope | Refresh, Publication, auth and health test modules; no unrelated backend suite claimed. |
| Static/document review | Receipt action/result enums match canonical OpenAPI; three Python files parse; 35 local links/anchors and document whitespace/fences passed. `git diff --check` passed; scoped source/test and documentation changes reviewed. |
| Runtime boundary | Opt-in test variables removed from the subprocess environment. No disposable PostgreSQL/Redis acceptance runner, retained database operation, EIA/S3 call, build, migration or live endpoint check performed. |

Affected-suite invocation used `python -m unittest -q` with sorted module stems matching `test_refresh*.py`, `test_publication*.py`, `test_auth*.py`, and `test_health.py`; PYTHONPATH contained this worktree's `src` and `tests`. This includes opt-in classes as explicit skips. Existing Starlette/httpx deprecation and sanitized pool messages remained; no dependency was changed.

The first test-file write used a repository-relative path from the backend directory and failed before creating a file; that discovery ran zero tests and is not counted as a pass. The initial broader harness loaded unittest from stdin; the auth scrypt subprocess could not reload `<stdin>`, producing one harness error (174 discovered, 59 passed, 114 skipped). Rerunning through the normal `-m unittest` entry point resolved that error without auth changes. The final candidate-identity case accounts for the extra discovered test.

Tests use explicit read-only row fixtures. They cover syntax, missing/repeated headers, body shape, existing/new receipt values, warning/slot/candidate linkage, old owner versus stop proof, dispatch/policy rejection, current publication generation, protected published/discarded work and database errors. They do not prove real writer termination, permission races, receipt replay effects or rollback; those remain later acceptance obligations.

Done: Step 2 code and offline regression. Pending: human explanation and Step 3 authorization. Blocker: no Step 2 code blocker; candidate lock-order correction is required before mutation integration.

Next: [ME] explain why an expired lease alone does not establish safe recovery.
