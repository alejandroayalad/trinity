# Tasks: One-table read-only SQL

Date: 2026-10-04
Status: First paired whole-input/single-SELECT check implemented; stop for review before further policy. No HTTP endpoint is authorized.
Branch/base: `feat/catalog-permissions`, `fde733b`; preserve concurrent catalog/API Docker work.
Basis: approved [specification](spec.md), [design](design.md), [proposal](proposal.md), A16/A19.
Evidence: [design/tasks session](../../ai/sessions/2026-10-04-single-table-sql-design-tasks.md).

## Human

**Current authorization:** after preparation, alayala supplied and authorized only the whole-input/single-statement validator flow. That function and ten focused tests are implemented; the full core validator remains incomplete. A24 trailing-comment handling needs review before completing this boundary. The [pairing review](pairing-gate.md) supplies the proposed cases and observed AST concepts. Alayala will review cases and implement or pair-program the validator. AI may add repetitive DataFusion compatibility infrastructure only after the validator works; alayala reviews failures and the security-sensitive execution path. Incremental local commits are authorized; pushes are not. This overrides autonomous execution of Step 2 below.

The next implementation stage is policy and engine compatibility. It must prove the agreed SQL forms, exact numbers and safe rejection before file downloads. The endpoint comes after storage, shared capacity and container termination are verified.

Viewer has no SQL button/editor/Run action and no direct API permission. Backend tests prove denial before SQL work. A later frontend slice proves hidden controls and direct-screen rejection; neither evidence substitutes for the other.

Stages below are bounded review gates. All unchecked implementation items are future work. A passing parser test or existing catalog suite does not complete this SQL slice. Maintain data evidence remains ongoing.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [x] T01 [ME] Approved the proposal, clarified Viewer exclusion, then requested design/tasks. [YOU] Recorded specification approval and D01–D03 in A16/A19 without claiming implementation approval.
- [x] T02 [YOU] Inspected current contracts, auth/DB/storage boundaries, installed library signatures and concurrent Docker files; drafted design/tasks and checked their documentation links/traceability.
- [ ] T03 [YOU] Recheck status/instructions and preserve current changes before each implementation stage. Explain input → processing → result and one failure case before code edits. Record actual human/AI contributions, corrections and measured checks in a unique implementation session.
- [ ] T04 [YOU] Maintain findings when real source evidence appears; synthetic fixtures do not create selected anomalies, prove completeness or authorize live publication. [ME] Own any EIA-key commands, builds/clicks and evaluator walkthrough.

Gate: design/tasks are reviewable. This ongoing duty stays open after implementation; current request authorizes only the bounded single-statement step described above.

### Step 2 — SQL policy and real engine compatibility

Requirements: R01–R07, R15–R17, R21. Scenarios: S01–S09, S17–S20 as applicable without a product endpoint.

- [ ] T05 [ME] Review the proposed matrix and implement or pair-program the core whole-input SQLGlot validator. [YOU] AST/API inspection and seven parser-characterization tests are complete; the supplied single-statement function and ten tests are now implemented, with A24 still a known gap. Stop before the table/token checks; closed query/policy messages remain pending. Cover every accepted D01 form and every populated AST argument; validate physical table/columns, typed dates, function arguments, comments and statement boundaries. Add bounded policy subprocess supervision, sanitized environment and timeout termination tests.
- [ ] T06 [ME] After the core review, pair with [YOU] on trusted identifier/projection normalization and ordered public label/unit mapping. Prove duplicate labels, exact mixed-case names, ORDER BY alias resolution, NULLS LAST and round-trip agreement without expanding SQL authority.
- [ ] T07 [YOU] Only after the validator works, add repetitive compatibility-test infrastructure. [ME] Review failures and the security-sensitive engine entrypoint. A later authorized implementation will provide a directly testable restricted DataFusion engine over temporary typed Parquet using selected options, one registered table and bounded output streaming. This is a test entrypoint, not a public route or an in-process production fallback.
- [ ] T08 [YOU] After the paired validator and [ME]-reviewed execution path exist, run focused policy/engine tests and record exact decimal precision/scales, AVG/division/ROUND behavior, overflow/type failure and row/byte limits. Complete the installed-version AST/config/numeric matrix in the design evidence. Preserve dependency pins. If accepted grammar cannot meet the semantics, stop at this gate with a concrete fixture/result and recommended correction.

Gate: all allowed forms have real engine evidence; adversarial input fails before guarded I/O; numerical semantics and parser limits are documented. No SQL route is registered yet.

### Step 3 — Trusted snapshots, shared accounting and file staging

Requirements: R02, R08–R13, R18–R22. Scenarios: S03, S10–S13, S15, S22–S27 at the state/storage boundary.

- [ ] T09 [YOU] Add the next reviewed Alembic revision for rolling user rate state, singleton admission and durable query reservations. Implement short service-owned transactions and conditional ownership; preserve existing auth deadlines/error behavior. Do not migrate a retained database.
- [ ] T10 [YOU] Add the two current-identity checks, committed D02 rate admission and coherent publication/manifest pin. Test exact boundary/counting outcomes, both no-publication/invalid-SQL orderings and concurrent publication changes using real disposable PostgreSQL connections.
- [ ] T11 [YOU] Implement a read-only published-manifest/staging operation using existing manifest/schema definitions and finite storage retry policy. Verify all selected files and local confinement; bound bytes/file counts and stage only generated request paths. Preserve preparation write behavior and its regression tests.
- [ ] T12 [YOU] Run cross-process rate/slot tests and staging tests for multiple files, corruption, denial, retry/deadline, symlink/path and partial-file failures. Prove Viewer causes no analytical counters, reservations or downloads. Record which reads use storage doubles and which use actual local bytes.

Gate: policy precedes all downloads; publication/artifact identity remains pinned; shared accounting holds across processes. All state/container uncertainty retains capacity. Still no route or claim of S3 credential isolation/live publication proof.

### Step 4 — Query container, supervision and recovery

Requirements: R07, R10–R15, R18–R23. Scenarios: S09, S13–S16, S20–S26.

- [ ] T13 [YOU] Add the narrow local Docker adapter and runtime entrypoint; implement bounded management calls and attach framing without a generic proxy or new Python dependency. Prepare the separate locked query image and only the necessary trusted API/recovery Compose additions. Preserve existing user Docker work. [ME] Build the prepared image when the exact command/artifacts are reviewable.
- [ ] T14 [YOU] Implement deadline-owned create/record/start, bounded message/result channels, fixed image/config inspection, request-only read-only volume subpath, no-network/no-secret restrictions and memory/process controls. Keep SQL off Docker argv/environment/labels/logs. No auto-pull or in-process fallback.
- [ ] T15 [YOU] Implement ownership fencing, stop/kill/inspect/removal and conditional release. Add the query-only recovery process and startup/periodic reconciliation. Cover late create/start, duplicate recovery, lost DB/daemon connection and cleanup failure; retain capacity when execution cannot be excluded.
- [ ] T16 [YOU] Run lifecycle doubles first. [ME] Start the prepared disposable container test environment. [YOU] Run real container acceptance only within that authorized environment: image identity/config, network/mount/secret denial, time/memory enforcement, output framing, API/supervisor crash recovery and no wrong-owner cleanup. Record platform/daemon/API/image IDs and actual stop evidence without credentials.

Gate: real containers establish isolation and termination; cross-process reservations remain correct throughout failure/recovery. Missing Docker, unsupported subpath or failed hardening is a blocker, not a reason to weaken the boundary. Do not register the execution route before this passes.

### Step 5 — HTTP integration, regression and operator handoff

Requirements: R01–R24. Scenarios: S01–S28, plus the API part of S29; S29 frontend remains pending separately.

- [ ] T17 [YOU] Wire `POST /api/v1/queries` and trusted lazy configuration/lifecycle. Use short auth/state transactions, validated policy and the supervisor; preserve health/auth/catalog/settings independence from unavailable query dependencies. Update the exact route inventory.
- [ ] T18 [YOU] Run real PostgreSQL + loopback HTTP + container flows with synthetic immutable published fixtures. Verify all personas, role/session changes, no-publication, queries for all three tables, safe errors/headers, 1,000-row truncation, 128-column/5-MiB limits and publication races. Validate complete serialized output against OpenAPI and report [] diagnostics accurately.
- [ ] T19 [YOU] Run focused suites then the full offline regression; separately run opt-in DB/container suites and report skips honestly. Review the focused diff and preservation hashes. Record commands, counts, timings, failures/corrections and all unverified boundaries; local incremental commits are authorized for this pairing gate; later commits, pushes and PRs need their own authorization.
- [ ] T20 [YOU] Write runnable setup/operator instructions from verified commands. [ME] Run one small retained-account check at a time and explain the denied-Viewer/pinned-publication/termination behavior. Keep UI hiding, live read-only storage and live publication evidence pending until observed; do not invent a successful query by promoting a candidate.

Gate: backend SQL acceptance complete only when its required evidence passes. The operator check and frontend SQL navigation remain separately visible. No local synthetic test is live EIA/S3 proof.

### Evidence checklist and current status

| Evidence | Current status | Completion owner/boundary |
|---|---|---|
| Specification, design/tasks and document checks | Drafted/checked; specification approved | [YOU] Documentation only; design choices still need implementation verification. |
| Policy, real engine and exact numbers | Ten single-statement tests and seven parser characterizations passed; full policy/engine acceptance not run | [YOU] Step 2 gate; no parser success treated as execution proof. |
| Real shared state and storage staging | Not run | [YOU] Step 3; no retained DB or cloud mutation. |
| Real query isolation, lifecycle and complete HTTP path | Not run | [ME] Builds/start; [YOU] authorized tests in Steps 4–5. |
| Retained-account, frontend and live published storage | Pending and separate | [ME] Operator/evaluator; frontend implementation remains outside this backend slice. |

Done: preparation and the first paired single-statement check; ten focused tests plus seven parser checks passed.
Pending: A24 comment handling review, then paired physical-table and token checks. DataFusion infrastructure follows only after the full validator works.
Blocker: A24 comment handling prevents full whole-input acceptance; later policy/engine/container acceptance remains unexecuted.

Next: [ME] review the A24 limitation in pairing-gate.md before expanding the check.
