# Tasks: Filtered, paginated dataset previews

Date: 2026-10-04
Status: alayala reviewed Step 3, authorized Steps 4–5 and requested closure/commit/push. Step 5 operator tooling is implemented; retained-account evidence remains incomplete. Step 4 automated PostgreSQL/HTTP/container acceptance passed with the user-built image; 432 distinct tests passed across the explicit suites. Preview execution remains disabled and retained publication linkage remains open. See [Step 4 evidence](../../ai/sessions/2026-10-04-dataset-preview-step-4-acceptance.md). Unchecked tasks are not completed evidence.
Branch: `feat/catalog-permissions`; catalog and SQL histories are reconciled here. See the [continuation record](../../ai/sessions/2026-10-04-catalog-sql-preview-reconciliation.md). Shared execution changes must preserve the existing SQL contracts.
Basis: [approved specification](spec.md), [design](design.md), A9/A15/A16/A19–A21, and [design/tasks evidence](../../ai/sessions/2026-10-04-dataset-preview-design-tasks.md).

Sequencing: alayala selected Step 5, Refresh and publication, as the next slice under [A16](../../DECISIONS.md#a16--approved-api-flow-and-detailed-contract). Alayala subsequently authorized preview Step 2 without an active publication. Real-data delivery still requires that publication lifecycle and complete frozen diagnostic provenance; keep the candidate unpublished until linkage is implemented and verified.

## Human

The slice adds one preview endpoint for role-permitted published rows. It reuses SQL's shared analytical counter, capacity, trusted staging and isolated runner. It adds strict filters, authenticated cursors, a typed runtime operation and an exact preview response. It does not implement a second executor or a SQL grammar change.

There are four bounded implementation stages after ongoing evidence work. Pass each stage's checks before continuing. Offline tests, real database/HTTP/container evidence and the retained-account operator check are separate. A stage cannot pass by skipping its required runtime checks or substituting an empty diagnostics adapter for missing frozen evidence.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Keep source values, FINDINGS and evidence boundaries current whenever later preview work encounters actual data. Synthetic fixtures are not new anomalies or completeness proof.
- [x] [ME] Approved the proposal and specification D01–D03; requested design/tasks. [YOU] Inspected shared SQL interfaces and drafted this bounded plan. This checkbox does not authorize implementation.
- [x] [ME] Authorized Step 2 only, without an active publication. [YOU] Explained input → flow → output and one failure before edits; preserved existing SQL files. This does not authorize later stages or publication.

### Step 2 — Strict request, cursor and response groundwork

Scope: R01–R09, R13–R17, R22. This stage adds pure components/tests; it does not expose a preview route.

- [x] [YOU] Reinspect current shared runtime/provenance interfaces and document the agreed integration point with the SQL workstream. Confirmed approved scope and inspected the initial source/test baseline without overwriting another terminal's work. Reuse existing frozen evidence; publication/preview linkage verification is deferred to Step 3. Inspection confirms the current publication reader exposes metadata/manifest identity but no frozen diagnostic projection. Actual publication-to-bundle linkage remains Step 3; evidence persistence is not missing.
- [x] [YOU] Add primitive/semantic parsing, canonical default resolution and complete-key validation in `queries/preview.py`; cover unknown/duplicate/blank inputs, one-bound defaults, leap-year ranges, ID preservation and incompatible filters. Verify the exact D02 pre-/post-debit boundary without real rate storage yet.
- [x] [YOU] Add the bounded HMAC cursor codec and lazy secret-safe key configuration. Test authentic/forged tokens, duplicate/deep JSON, all bound fields, purpose/key/version, overlength/Unicode limits, stable restart and retirement. Prove worst-case valid source IDs fit the public cursor bound. No real key is committed or printed.
- [x] [YOU] Add closed PreviewResponse/diagnostic models and canonical column reuse, exact decimal/date/null encoding and whole-response limits. Cover empty-first-page versus broken continuation, lookahead flags and prohibited extra SQL fields. Require frozen diagnostic input rather than defaulting missing provenance to [].
- [x] [YOU] Run focused offline tests and review this stage's diff. Record counts/skips and preserve existing auth/catalog/SQL contracts.
- [ ] [ME] Review the concrete continuation example in the Step 2 evidence; record only an observed explanation, not inferred understanding.

Gate: pure contract checks pass. Runtime and database evidence remain pending. Saved frozen evidence is confirmed; its connection to publication/preview and shared-runner readiness remain integration checks.

### Step 3 — Shared typed execution and endpoint integration

Scope: R02–R03, R07–R23. Coordinate mutations of shared SQL files explicitly within the authorized implementation stage.

- [x] [YOU] Extend the shared operation contract with the typed preview payload and tagged/versioned envelopes. Update staging producer, runtime dispatch and result reader together; preserve SQL payload/policy revalidation and reject cross-kind/version confusion. Share the restricted engine context/serializer rather than copying lifecycle code.
- [x] [YOU] Implement typed DataFusion date/ID/full-key predicates, binary complete-key ordering and bounded lookahead. Add real temporary-Parquet engine fixtures for all three schemas, repeated dates/entities, Unicode/leading-zero IDs and exact decimal/null values. Verify no client expression/path enters execution.
- [ ] [YOU] **Retained publication linkage remains unverified.** Implemented the read path active publication → version/manifest → trusted bundle/attempt/checkset → frozen diagnostics, plus offline hash/projection tests and compatibility with the existing synthetic producer. Drafted only the proven two-column index gap in `0004_preview_evidence`; Step 3 applied no migration, and Step 4 applies it only to disposable test clusters. The October 1–2 bundle remains unchanged and unpublished. Actual writer/population/linkage verification is pending; do not regenerate evidence, activate the candidate or implement refresh commands implicitly. Applying the retained-database migration requires separate explicit approval.
- [x] [YOU] Add PreviewService with the specified identity → shape → committed rate → semantic/cursor → publication/default/provenance → capacity sequence. Add the GET route and shared disconnect handling, lazy trusted configuration and full response validation/cursor signing. Keep the route unenabled for delivery until provenance and shared isolation pass; no callable path may fall back to API-process execution or mocks.
- [x] [YOU] Extend the shared supervisor result handling without weakening termination/cleanup, and test fake lifecycle failures before runtime acceptance. Review source/docstrings under CONTRIBUTING and run relevant SQL/auth/catalog regressions after shared edits. Record remaining configuration and image compatibility needs.

Implementation evidence: typed protocol/engine, service/route, frozen-evidence projection and shared lifecycle changes pass focused offline checks. A synthetic fixture from the existing real producer verifies bundle compatibility; this is not the retained publication. `0004_preview_evidence` adds the two missing references without backfilling them; it has run only in Step 4 disposable clusters. Producer/readback bytes for the October 1–2 candidate remain unchanged. See the [measured checks and limits](../../ai/sessions/2026-10-04-dataset-preview-step-3.md).

Gate: offline integration code is verified. Complete authoritative **retained publication linkage remains pending**, while Step 4 separately verifies disposable migration execution and the user-built image. Preview execution remains disabled; Step 4 authorization and measured database/HTTP/container acceptance are recorded below. SQL policy behavior and its human review boundary remain unchanged.

### Step 4 — Real PostgreSQL, HTTP and container acceptance

Scope: R01–R24; all R evidence scenarios below. This is the automated runtime evidence category, with separate database/HTTP/engine/container results. [ME] Reviewed Step 3 and explicitly authorized Step 4. [YOU] Added `--preview`/`--all` to the disposable runner, complete producer-backed synthetic fixtures, database/HTTP checks and matching-image real-container scenarios. Migration 0004 has run only in disposable test clusters. Current results and skips are in the [acceptance record](../../ai/sessions/2026-10-04-dataset-preview-step-4-acceptance.md).

- [x] [YOU] Extend the existing disposable SQL database runner/fixtures to include preview acceptance; never point destructive test setup at the retained application database. Seed complete synthetic publication/diagnostic evidence only inside the disposable fixture and record exact fixture limits. Verify migrations in that environment; do not apply them to the user's Docker database automatically.
- [x] [YOU] Exercise the actual HTTP route with all roles, current-role/session changes, headers and exact OpenAPI serialization. Coordinate independent connections for publication races and prove later continuation behavior, equivalent defaults and invalid-cursor rejection before downloads. Verify no long metadata transaction spans engine/storage work.
- [x] [YOU] Prove mixed SQL/preview rolling rate and capacity across processes, D02 failure accounting, cursor replay counts, boundary times, no double debit on retries and no release of another operation's reservation. Fail-closed tests must cover unavailable PostgreSQL/signing/provenance/storage/runtime configuration.
- [x] [ME] Build the matching shared query image and supply the explicit isolated local test configuration when needed. [YOU] Run real container/network/mount/resource tests and lifecycle fault injection: timeout during staging/start/execution, memory/output caps, disconnect, ambiguous launch, crash recovery, stale owner and unknown termination. Confirm actual stop/removal/cleanup before capacity release; report concrete timing and retained reservations on uncertainty.
- [x] [YOU] Run the required combined regression suite once the focused checks pass, inspect the final diff and update measured evidence. Distinguish real loopback HTTP from TestClient, real engine fixtures from Docker, and synthetic storage from real S3. Record skips as pending, never as passes. Do not claim live EIA/S3 completeness from these checks.

Gate passed for automated evidence: all required preview and shared-runtime checks pass with no unresolved test failure. This proves the synthetic fixture and isolated test runtime, not retained publication provenance. Readiness requires both trusted published provenance and matching deployed runtime protocol. Test success does not authorize publishing retained data or starting the user's operator flow with a fabricated publication.

**Shared-runtime follow-up:** [Ten query-guarantee cases](../../ai/sessions/2026-10-04-query-guarantees-fault-acceptance.md) passed with real Docker/PostgreSQL: distinct V1/V2 values and cross-request cleanup, SQL plus sandbox isolation, lifecycle races, actual reply loss and natural-expiry recovery through a separate entry point. These checks strengthen Step 4; they do not enable Preview or close the retained-account gate. The final combined regression passed 82/82 with zero skips; the record preserves earlier intermittent setup-login failures without claiming their cause was fixed.

### Step 5 — Operator check and handoff

[ME] Authorized Step 5, closure and commit/push to this branch. [YOU] Added the optional checker and a concrete candidate fixture description. The retained operator gate remains incomplete: read-only inspection found migration 0002 and zero publications. See the [handoff](../../ai/sessions/2026-10-04-dataset-preview-step-5-handoff.md). Closure must preserve this boundary.

Scope: R24, S31 and the human checks in the matrix. This completes retained-account evidence only after its prerequisites exist.

- [x] [YOU] Add an optional preview mode to the existing private-input persona checker without changing default/auth/catalog behavior. Use each login token only in memory, ensure logout on failure, check role-safe responses and verify at least one real continuation. Do not print passwords, tokens, cursor contents or sensitive response bodies.
- [ ] [YOU] **Candidate description supplied; authorized publication fixture blocked.** Provide a concrete operator fixture description: selected authorized publication/date range/entity and page size with known expected matching keys, sufficient records for a second page, and completed diagnostic evidence. Missing publication or insufficient observations must report “not ready/incomplete,” not a passing preview check. Do not introduce automatic seeding/publication into the checker.
- [ ] [ME] Supply configuration/keys privately and run the documented check with retained Viewer, Analyst and Admin accounts against that known publication. [YOU] Observe safe pass/fail evidence for national-only Viewer access, detail denial, all three Analyst/Admin datasets, exact entity filtering and next-page continuity. A publication-change demonstration uses separately authorized state changes only; automated race evidence remains separate.
- [x] [YOU] Update backend/root README, SDD status, NOTES and a unique session with commands, counts, runtime results, operator evidence and remaining limits. Check links and review the final scoped diff. Keep frontend/entity-choice/dashboard/query-history/export work explicitly later.
- [ ] [ME] Review the distinction between a cursor, current permission and publication identity. Commits and push are authorized; PR/merge remain unrequested. [YOU] Close only completed evidence gates and preserve unsquashed history.

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

### Verification commands — measured status in Step 4 evidence

Follow the repository's unittest workflow. These files and runner options now exist. Use the existing locked environment. The acceptance record gives exact pass/skip counts and runtime prerequisites.

| Purpose | Command from backend/ |
|---|---|
| Pure input/cursor/response checks | `.venv/bin/python -m unittest discover -s tests -p 'test_preview_unit.py' -v` |
| Exact temporary-Parquet engine fixtures | `.venv/bin/python -m unittest discover -s tests -p 'test_preview_engine.py' -v` |
| Disposable PostgreSQL/HTTP and combined regression | `.venv/bin/python tests/run_local_sql_checks.py --all` |
| Explicitly configured real preview containers | `.venv/bin/python tests/run_local_sql_checks.py --runtime-only` |
| Offline regression, runtime opt-ins disabled | `env -u TRINITY_TEST_DATABASE_URL -u TRINITY_TEST_QUERY_IMAGE .venv/bin/python -m unittest discover -s tests -v` |

Use `uv run --locked python` equivalents when the supported uv environment is available. Set `TRINITY_TEST_QUERY_IMAGE` to the matching immutable image ID and `TRINITY_TEST_DOCKER_SOCKET` to the local daemon socket for real-container acceptance. The default suite may skip runtime checks, so it cannot replace explicit PostgreSQL/container results. Use `git diff --check` plus focused link/OpenAPI checks for documentation. No formatter/linter/type-check command is assumed without checking the then-current pyproject configuration.

### Current checkpoint

Done: Steps 2–4 implementation and automated acceptance; Step 5 guarded checker and concrete candidate handoff. Commit/push is authorized.
Pending: a real publication fixture and the retained Viewer/Analyst/Admin operator run; no human explanation of cursor/permission/publication identity is inferred.
Blocker for delivery: retained migration is 0002, with zero publications; authoritative publication linkage and runtime configuration must exist before enabling preview. Applying migrations alone does not publish data.
Next: implement the accepted refresh/publication slice before attempting the retained operator check. See the [closure record](../../ai/sessions/2026-10-04-dataset-preview-step-5-handoff.md).
