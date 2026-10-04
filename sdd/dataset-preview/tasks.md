# Tasks: Filtered, paginated dataset previews

Date: 2026-10-04
Status: Design/tasks drafted after alayala approved specification D01–D03 and requested continuation. Implementation is not authorized. Unchecked tasks are future work, not completed evidence.
Branch: `feat/catalog-permissions`; catalog and SQL histories are reconciled here. See the [continuation record](../../ai/sessions/2026-10-04-catalog-sql-preview-reconciliation.md). Shared execution changes must preserve the existing SQL contracts.
Basis: [approved specification](spec.md), [design](design.md), A9/A15/A16/A19–A21, and [design/tasks evidence](../../ai/sessions/2026-10-04-dataset-preview-design-tasks.md).

## Human

The slice adds one preview endpoint for role-permitted published rows. It reuses SQL's shared analytical counter, capacity, trusted staging and isolated runner. It adds strict filters, authenticated cursors, a typed runtime operation and an exact preview response. It does not implement a second executor or a SQL grammar change.

There are four bounded implementation stages after ongoing evidence work. Pass each stage's checks before continuing. Offline tests, real database/HTTP/container evidence and the retained-account operator check are separate. A stage cannot pass by skipping its required runtime checks or substituting an empty diagnostics adapter for missing frozen evidence.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Keep source values, FINDINGS and evidence boundaries current whenever later preview work encounters actual data. Synthetic fixtures are not new anomalies or completeness proof.
- [x] [ME] Approved the proposal and specification D01–D03; requested design/tasks. [YOU] Inspected shared SQL interfaces and drafted this bounded plan. This checkbox does not authorize implementation.
- [ ] [ME] Authorize a concrete implementation stage or all stages. [YOU] Before edits, restate input → data flow → output and one failure tied to that stage; preserve concurrent SQL work.

### Step 2 — Strict request, cursor and response groundwork

Scope: R01–R09, R13–R17, R22. This stage adds pure components/tests when authorized; it does not expose a preview route.

- [ ] [YOU] Reinspect current shared runtime/provenance interfaces and document the agreed integration point with the SQL workstream. Confirm approved scope and initial source/test baseline; do not branch/reset/overwrite another terminal's work. Verify the A9 diagnostic producer/read model and record its exact availability before promising runtime delivery.
- [ ] [YOU] Add primitive/semantic parsing, canonical default resolution and complete-key validation in `queries/preview.py`; cover unknown/duplicate/blank inputs, one-bound defaults, leap-year ranges, ID preservation and incompatible filters. Verify the exact D02 pre-/post-debit boundary without real rate storage yet.
- [ ] [YOU] Add the bounded HMAC cursor codec and lazy secret-safe key configuration. Test authentic/forged tokens, duplicate/deep JSON, all bound fields, purpose/key/version, overlength/Unicode limits, stable restart and retirement. Prove worst-case valid source IDs fit the public cursor bound. No real key is committed or printed.
- [ ] [YOU] Add closed PreviewResponse/diagnostic models and canonical column reuse, exact decimal/date/null encoding and whole-response limits. Cover empty-first-page versus broken continuation, lookahead flags and prohibited extra SQL fields. Require frozen diagnostic input rather than defaulting missing provenance to [].
- [ ] [YOU] Run focused offline tests and review this stage's diff. Record counts/skips and preserve existing auth/catalog/SQL contracts. [ME] Review one concrete cursor continuation example; record only an observed explanation, not inferred understanding.

Gate: pure contract checks pass. Runtime and database evidence remain pending. Missing shared runner/provenance does not prevent pure work, but blocks later real endpoint delivery.

### Step 3 — Shared typed execution and endpoint integration

Scope: R02–R03, R07–R23. Coordinate mutations of shared SQL files explicitly within the authorized implementation stage.

- [ ] [YOU] Extend the shared operation contract with the typed preview payload and tagged/versioned envelopes. Update staging producer, runtime dispatch and result reader together; preserve SQL payload/policy revalidation and reject cross-kind/version confusion. Share the restricted engine context/serializer rather than copying lifecycle code.
- [ ] [YOU] Implement typed DataFusion date/ID/full-key predicates, binary complete-key ordering and bounded lookahead. Add real temporary-Parquet engine fixtures for all three schemas, repeated dates/entities, Unicode/leading-zero IDs and exact decimal/null values. Verify no client expression/path enters execution.
- [ ] [YOU] Implement trusted pinning/projection of complete frozen publication diagnostics using the canonical A9 evidence source. Reuse a completed producer/read model if present. If persistence is absent, identify the exact prerequisite migration/producer ownership and stop that integration path; do not fabricate evidence, activate a candidate or implement refresh commands implicitly. Any retained-database migration needs its separate explicit approval.
- [ ] [YOU] Add PreviewService with the specified identity → shape → committed rate → semantic/cursor → publication/default/provenance → capacity sequence. Add the GET route and shared disconnect handling, lazy trusted configuration and full response validation/cursor signing. Keep the route unenabled for delivery until provenance and shared isolation pass; no callable path may fall back to API-process execution or mocks.
- [ ] [YOU] Extend the shared supervisor result handling without weakening termination/cleanup, and test fake lifecycle failures before runtime acceptance. Review source/docstrings under CONTRIBUTING and run relevant SQL/auth/catalog regressions after shared edits. Record remaining configuration and image compatibility needs.

Gate: integration code passes focused offline/engine tests with exact versioned bindings; complete authoritative provenance is available. Route enablement and runtime completion claims still wait for Step 4. SQL policy behavior and its human review boundary remain unchanged.

### Step 4 — Real PostgreSQL, HTTP and container acceptance

Scope: R01–R24; all R evidence scenarios below. This is the automated runtime evidence category, with separate database/HTTP/engine/container results.

- [ ] [YOU] Extend the existing disposable SQL database runner/fixtures to include preview acceptance; never point destructive test setup at the retained application database. Seed complete synthetic publication/diagnostic evidence only inside the disposable fixture and record exact fixture limits. Verify migrations in that environment; do not apply them to the user's Docker database automatically.
- [ ] [YOU] Exercise the actual HTTP route with all roles, current-role/session changes, headers and exact OpenAPI serialization. Coordinate independent connections for publication races and prove later continuation behavior, equivalent defaults and invalid-cursor rejection before downloads. Verify no long metadata transaction spans engine/storage work.
- [ ] [YOU] Prove mixed SQL/preview rolling rate and capacity across processes, D02 failure accounting, cursor replay counts, boundary times, no double debit on retries and no release of another operation's reservation. Fail-closed tests must cover unavailable PostgreSQL/signing/provenance/storage/runtime configuration.
- [ ] [ME] Build the matching shared query image and supply the explicit isolated local test configuration when needed. [YOU] Run real container/network/mount/resource tests and lifecycle fault injection: timeout during staging/start/execution, memory/output caps, disconnect, ambiguous launch, crash recovery, stale owner and unknown termination. Confirm actual stop/removal/cleanup before capacity release; report concrete timing and retained reservations on uncertainty.
- [ ] [YOU] Run the required combined regression suite once the focused checks pass, inspect the final diff and update measured evidence. Distinguish real loopback HTTP from TestClient, real engine fixtures from Docker, and synthetic storage from real S3. Record skips as pending, never as passes. Do not claim live EIA/S3 completeness from these checks.

Gate: all required preview and shared-runtime checks pass with no unresolved authority, provenance, isolation, cleanup or output failure. Readiness requires both trusted published provenance and matching deployed runtime protocol. Test success does not authorize publishing retained data or starting the user's operator flow with a fabricated publication.

### Step 5 — Operator check and handoff

Scope: R24, S31 and the human checks in the matrix. This completes retained-account evidence only after its prerequisites exist.

- [ ] [YOU] Add an optional preview mode to the existing private-input persona checker without changing default/auth/catalog behavior. Use each login token only in memory, ensure logout on failure, check role-safe responses and verify at least one real continuation. Do not print passwords, tokens, cursor contents or sensitive response bodies.
- [ ] [YOU] Provide a concrete operator fixture description: selected authorized publication/date range/entity and page size with known expected matching keys, sufficient records for a second page, and completed diagnostic evidence. Missing publication or insufficient observations must report “not ready/incomplete,” not a passing preview check. Do not introduce automatic seeding/publication into the checker.
- [ ] [ME] Supply configuration/keys privately and run the documented check with retained Viewer, Analyst and Admin accounts against that known publication. [YOU] Observe safe pass/fail evidence for national-only Viewer access, detail denial, all three Analyst/Admin datasets, exact entity filtering and next-page continuity. A publication-change demonstration uses separately authorized state changes only; automated race evidence remains separate.
- [ ] [YOU] Update backend/root README, SDD status, NOTES and a unique session with commands, counts, runtime results, operator evidence and remaining limits. Check links and review the final scoped diff. Keep frontend/entity-choice/dashboard/query-history/export work explicitly later.
- [ ] [ME] Review the distinction between a cursor, current permission and publication identity. Authorize commits/push/PR separately if wanted. [YOU] Close only completed evidence gates and preserve unsquashed history.

Gate: all three evidence categories have recorded results. If retained publication/operator prerequisites are absent, hand off that exact pending boundary without calling the complete preview slice verified.

### Scenario-to-stage coverage

| Scenarios | Main stage / proof |
|---|---|
| S01–S03 | Steps 3–4 actual route/identity matrix and denial guards; Step 5 retained personas. |
| S04–S09 | Step 2 strict-input/default/ID tests; Steps 3–4 exact engine and HTTP results. |
| S10–S12 | Steps 2–3 page boundary/complete-key fixture proof; Steps 4–5 HTTP replay and continuation. |
| S13–S14 | Step 2 cursor authenticity/binding; Step 4 current authority and cross-account replay. |
| S15–S17 | Step 4 synchronized publication races and broken/empty state; Step 5 no automatic publication changes. |
| S18–S21 | Steps 2–3 serializer/provenance guards and typed engine fixtures; Step 4 privacy/runtime failures; Step 5 observed source values. |
| S22–S23 | Step 4 cross-process mixed-operation rate/capacity with real PostgreSQL. |
| S24–S25 | Steps 3–4 verified staging and actual isolated container denials; mocks are insufficient for S25. |
| S26–S28 | Step 4 measured deadlines/retries/resources, disconnect/crash/ownership cleanup; selected offline fault injection earlier. |
| S29–S30 | Steps 2–4 key/configuration lifecycle, real HTTP/OpenAPI and regressions; actual keys remain private. |
| S31 | Step 5 retained-account operator evidence over a known publication. |

All S01–S31 map back to R01–R24 in the approved specification. The detailed design supplies the implementation mechanics without changing the spec's public fields or D01–D03.

### Planned commands — not executed by this planning request

Follow the repository's unittest workflow. Proposed preview test filenames are future artifacts, not claims that these commands currently find tests. Use the existing locked environment; do not install or change dependencies as part of planning.

| Purpose | Planned command from backend/ |
|---|---|
| Pure input/cursor/response checks | `.venv/bin/python -m unittest discover -s tests -p 'test_preview_unit.py' -v` |
| Exact temporary-Parquet engine fixtures | `.venv/bin/python -m unittest discover -s tests -p 'test_preview_engine.py' -v` |
| Disposable PostgreSQL/HTTP, after runner extension | `.venv/bin/python tests/run_local_sql_checks.py` |
| Explicitly configured real preview containers | `.venv/bin/python -m unittest discover -s tests -p 'test_preview_containers.py' -v` |
| Full regression | `.venv/bin/python -m unittest discover -s tests -v` |

Use `uv run --locked python` equivalents when the supported uv environment is available. Runtime opt-in/configuration must be documented during implementation; do not invent environment flags before tests exist. The default suite may skip runtime checks, so it cannot replace explicit PostgreSQL/container results. Use `git diff --check` plus focused link/OpenAPI checks for documentation. No formatter/linter/type-check command is assumed without checking the then-current pyproject configuration.

### Current checkpoint

Done: approved specification and drafted design/tasks, with shared SQL integration and complete diagnostic provenance made explicit.
Pending: implementation authorization; all preview tests/runtime/operator results.
Blocker: no planning blocker. Missing frozen diagnostic provenance or unverified shared runtime blocks endpoint delivery, not pure contract work.
Next: [ME] authorize Step 2 or choose the implementation scope.
