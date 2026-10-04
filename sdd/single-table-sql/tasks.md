# Tasks: One-table read-only SQL

Date: 2026-10-04
Status: Backend implemented, committed and pushed. Completed implementation and measured checks are marked below; remaining verification is listed separately.
Branch: `feat/catalog-permissions` (the synchronized delivery branch is a reference, not a separate workstream).
Basis: approved [specification](spec.md), [design](design.md), [proposal](proposal.md), A16/A19.
Evidence: [policy/engine implementation](../../ai/sessions/2026-10-04-sql-full-implementation.md), [isolation/HTTP delivery](../../ai/sessions/2026-10-04-sql-delivery-commits.md), and [combined-branch verification](../../ai/sessions/2026-10-04-catalog-sql-preview-reconciliation.md).

## Human

**SQL is implemented.** SQLGlot validates the complete request before published-file downloads. The service pins one published version, admits shared work, verifies files, and executes the query with DataFusion in a restricted container. `POST /api/v1/queries` is registered. Viewer is denied before SQL work; hiding frontend controls remains a later frontend responsibility.

Alayala supplied the initial paired single-statement flow, clarified the terminal-semicolon rule, then authorized autonomous T05–T20 and Git delivery. The earlier pairing-only stop is historical. See the [pairing evidence](../../ai/sessions/2026-10-04-sql-single-statement-pairing.md) and [semicolon correction](../../ai/sessions/2026-10-04-sql-terminal-comment-pairing.md). Original task wording remains in Git history; this checklist reports current state.

A checked implementation item means its code or named verification exists. It does not close a separately unchecked acceptance item. T01–T20 identifiers are retained; suffixes distinguish unfinished portions of a task that previously combined implementation and verification.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [x] T01 [ME] Approved proposal/specification and Viewer exclusion. [YOU] Recorded the selected D01–D03 rules in A16/A19.
- [x] T02 [YOU] Inspected canonical contracts, installed parser/engine interfaces and existing auth/storage boundaries; prepared the design and review matrix.
- [x] T03 [YOU] Inspected and preserved existing work, explained the bounded implementation flows, recorded contributions/checks, and reconciled catalog/SQL histories without rewriting them. Evidence: the implementation, delivery and reconciliation records above.
- [ ] T04 [YOU] Maintain findings whenever future work produces real source evidence. Synthetic fixtures do not prove live completeness or authorize publication. [ME] Own evaluator/live-data actions within their explicit authorization.

The ongoing data-evidence duty remains open across all slices.

### Step 2 — SQL policy and real engine compatibility

Requirements: R01–R07, R15–R17, R21. Scenarios: S01–S09, S17–S20 at the policy/engine boundary.

- [x] T05 [YOU] Implement whole-input statement, token, physical-table, column, function/date spelling and closed-AST checks, plus bounded policy subprocess supervision. Evidence: `queries/runtime/sql_policy.py`, `queries/policy.py`, `test_sql_single_statement.py`, `test_sql_policy.py` and parser characterization tests. The review matrix contains 25 allowed and 52 rejected fixtures.
- [x] T06 [YOU] Implement trusted quoting, projection/alias normalization, duplicate public labels, ordered unit mapping, explicit null ordering and policy-message round-trip checks. Canonical qualifiers with a table alias have a regression test (`1e3c072`).
- [x] T07 [YOU] Implement a directly testable restricted DataFusion engine over temporary canonical Parquet, one registered table and bounded exact output. Evidence: `queries/runtime/engine.py`, `tests/sql_fixture.py` and `test_sql_engine.py`. Production uses the container supervisor.
- [x] T08 [YOU] Execute every allowed review fixture and record decimal scales, AVG/division/ROUND, nulls, overflow/type failure and row/byte limits without changing dependency pins. Ten engine tests passed at delivery. Exact observations, including the measured ROUND scale range, are in the [policy/engine record](../../ai/sessions/2026-10-04-sql-full-implementation.md#t05t08-evidence).

Result: policy and real-engine compatibility are implemented and tested. No further paired-validator implementation gate remains.

### Step 3 — Trusted snapshots, shared accounting and file staging

Requirements: R02, R08–R13, R18–R22. Scenarios: S03, S10–S13, S15, S22–S27 at the state/storage boundary.

- [x] T09 [YOU] Add `0003_query_admission`, rolling rate state, singleton capacity admission and durable fenced reservations. Use short service-owned transactions. The migration and auth regressions ran against disposable PostgreSQL.
- [x] T10 [YOU] Implement both current-identity checks, committed rate debits and publication/manifest pinning. Tests cover role change during policy, invalid SQL before no-publication, exact rolling boundaries/clock regression, retained capacity on expiry and publication-pointer changes.
- [x] T11 [YOU] Implement GET-only pinned-manifest staging with existing contracts, bounded retry/bytes/file counts, checksums/schema/row counts, generated request paths and cleanup. Evidence: `queries/staging.py` and six staging tests using synthetic storage responses and actual local Parquet bytes.
- [x] T12 [YOU] Verify independent-process rate/global capacity limits, selected multifile staging, corruption, retries/deadlines, symlinks and partial cleanup. Prove Viewer denial before policy/counters/configuration and downloads through the SQL service and HTTP tests.

Result: shared admission and verified staging are implemented. Live S3 credential restrictions and the full end-to-end scenario matrix remain under the verification list below.

### Step 4 — Query container, supervision and recovery

Requirements: R07, R10–R15, R18–R23. Scenarios: S09, S13–S16, S20–S26.

- [x] T13 [YOU] Add the local Docker adapter, bounded attach framing, runtime entrypoint, locked query image and API/recovery Compose configuration. The query image was built from the staged source snapshot; Compose configuration passed validation.
- [x] T14 [YOU] Implement durable create/start state, fixed image/config checks, request-only read-only volume subpath, network/credential isolation, memory/process limits and bounded messages/results. SQL stays out of Docker argv/environment/labels/logs.
- [x] T15 [YOU] Implement ownership fencing, stop/kill/inspect/removal, conditional capacity release and query-only recovery. Lifecycle tests cover absent ambiguous create, removal-before-release, daemon/cleanup failures, wrong daemon and revoked owner. Real PostgreSQL/container recovery covers an expired running reservation, duplicate recovery and stale-owner denial.
- [x] T16 [YOU] Run the seven standalone Docker/frame checks: real query results, fixed restriction inspection, network/mount/sibling/credential denial probes, kernel memory ceiling, timeout removal, wrong-owner rejection and bounded framing. Platform/image/API details and probe limitations are recorded in [delivery evidence](../../ai/sessions/2026-10-04-sql-delivery-commits.md).
- [ ] T15-V [YOU] Complete the remaining late-create/start and lost-connection/interleaving acceptance cases. Existing failure tests do not establish every lifecycle race.
- [ ] T16-V [YOU] Inject an actual API/supervisor-process crash and verify recovery/termination. The current real recovery test abandons a running reservation; it does not kill the supervisor process.

Result: isolated execution/recovery code and the listed real-container checks are complete; the remaining failure-injection cases are explicit.

### Step 5 — HTTP integration, regression and operator handoff

Requirements: R01–R24. Scenarios: S01–S28 and the API portion of S29; frontend S29 remains separate.

- [x] T17 [YOU] Register `POST /api/v1/queries`, bounded request/response models, lazy trusted configuration, disconnect cancellation and supervised execution. The route inventory retains both catalog and SQL.
- [x] T18 [YOU] Run real PostgreSQL + loopback HTTP + Docker with synthetic immutable publication fixtures. Verify Viewer denial, Analyst/Admin exact results, pinned publication, safe errors/headers and confirmed cleanup. Record the test-only staging-volume bridge and synthetic GET client rather than claiming live storage/Compose proof.
- [ ] T18-V [YOU] Complete the full original HTTP acceptance matrix: all three datasets, additional session/publication race cases, serialized OpenAPI conformance and row/column/byte boundary scenarios through the complete HTTP/container path. Existing engine/service tests prove only their own tested boundaries.
- [x] T19 [YOU] Run focused and full regression suites, separate opt-in database/container evidence from skips, review diffs and preservation, and commit/push the reconciled histories. Latest combined run: 344 discovered, 292 passed and 52 opt-in skips; separately, 70 auth/catalog checks and all 11 SQL database/HTTP/container checks passed. Earlier standalone Docker evidence remains recorded; those five real probes were not rerun during reconciliation.
- [x] T20 [YOU] Deliver [SQL operator instructions](../../backend/SQL.md) and record setup/configuration requirements, recovery behavior, tested commands and limits.
- [ ] T20-V [ME] Verify the full deployed SQL Compose wiring, retained-account query and dedicated published-object read authority. Existing catalog operator evidence and connector S3 evidence do not establish SQL's live execution path. Preserve publication rules; do not promote a candidate merely to make the check run.
- [ ] T20-UI [YOU] In the later frontend slice, verify hidden Viewer SQL controls and denied direct SQL-screen access. Backend Viewer denial is already tested.

## Current checkpoint

Done: SQL backend implementation, the recorded policy/engine/storage/admission/container/HTTP checks, operator documentation and Git delivery.
Pending: T15-V, T16-V, T18-V, T20-V and later frontend T20-UI; T04 remains an ongoing duty.
Blocker: none for acknowledging completed implementation or beginning preview groundwork. The unchecked items remain real verification work.

Next: [ME] continue with [preview tasks Step 2](../dataset-preview/tasks.md#step-2--strict-request-cursor-and-response-groundwork); preview currently contains planning only.
