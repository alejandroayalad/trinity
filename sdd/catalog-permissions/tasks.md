# Tasks: Catalog and permissions

Date: 2026-10-04
Status: Implemented and automated-tested October 4, 2026 after alayala authorized implementation. The [implementation evidence](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md) separates offline, database/HTTP and operator evidence. Retained-account Docker operator verification passed in the no-publication state; see [operator evidence](../../ai/sessions/2026-10-04-catalog-docker-operator-check.md).
Branch: `feat/catalog-permissions`
Basis: [proposal](proposal.md), approved [specification](spec.md), [design](design.md), A9/A15–A17/A19–A21.

Current focused delivery: [review and verification](../../ai/sessions/2026-10-04-catalog-review-and-delivery.md). On the delivery branch, 239 offline tests passed (36 database skips); all 70 auth/catalog acceptance checks passed separately. Earlier counts below describe the initial implementation run.

## Human

The specification is approved, including newest-attempt freshness. The implementation provides national-only Viewer metadata and all-three-dataset metadata for Analyst/Admin. Viewer remains dashboard-only in the later interface.

The implementation has four bounded stages after the ongoing evidence duty: metadata/policy, the endpoint and state reads, runtime acceptance, then handoff. Each stage leaves a reviewable result. Checked items below have implementation or recorded test evidence; the retained-account operator check passed; the human behavior review remains open.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [x] [ME] Approved the specification, including D01, and requested design/tasks. [YOU] Recorded the accepted freshness refinement in A16 and the API contract.
- [ ] [YOU] Preserve unrelated working changes and keep source-data findings current if later work produces new evidence. Catalog's synthetic fixtures do not create new anomaly findings or prove live storage/publication.
- [x] [ME] Authorized implementation of all stages. [YOU] Explained input → flow → output and the failed-refresh/database-outage distinction before code changes. Alayala reserved the local operator check for himself.

Gate: specification/design/tasks implemented under the explicit implementation request. The ongoing evidence duty remains open after slice delivery.

### Step 2 — Canonical metadata and shared permissions

Scope: R02–R06, R10, R14; S03, S04, S08, S21 and relevant S22 regressions.

- [x] [YOU] Recheck branch/status and current canonical definitions; read CONTRIBUTING before edits. Add catalog package, closed models and registry tied to `DATASETS`, with exact public keys, columns, daily keys, units, filters and the one national metric definition.
- [x] [YOU] Expose permitted internal dataset keys from the existing permission module; make `require_dataset` reuse that rule. Preserve Viewer capabilities and safe denials. Fail on missing allowed definitions instead of silently omitting them.
- [x] [YOU] Add focused metadata/policy/serialization tests covering all roles, exact wire shapes, canonical type mapping, mutable-response isolation and missing/invalid static definitions.
- [x] [YOU] Run the focused offline checks and relevant existing policy tests; inspect the diff and record actual results. Explain how internal `national` becomes public `national_outages` without granting extra access.

Gate: static metadata and shared permissions verified by the 16 focused offline catalog tests and existing auth regressions.

### Step 3 — Catalog endpoint and consistent state

Scope: R01–R13; S01, S02, S05, S09, S10, S12–S15, S18–S20 and S21 HTTP behavior.

- [x] [YOU] Add the fixed three-field `read_last_refresh` projection to the refresh repository using highest `run_seq`. Preserve Admin context reads and existing publication authority.
- [x] [YOU] Implement `get_catalog` and the single authenticated route; register it in `main.py`. Use one supplied read-only snapshot for identity, active publication and refresh. Build fresh responses with exact null/UTC semantics.
- [x] [YOU] Separate persisted-state validation failures from invalid static definitions. Reuse transport/auth errors, no-store headers and database bounds. Add no external I/O, analytical slots, migrations or production dependencies.
- [x] [YOU] Test the production HTTP route with controlled doubles for all persona sets, before/after publication, safe failures, rejected inputs, headers and forbidden operation calls. Run focused checks and review the diff.

Gate: catalog route passes offline acceptance; step 4 separately verifies real session/database/race behavior.

### Step 4 — Real PostgreSQL and HTTP acceptance

Scope: R07–R13, R15; S06, S07, S10–S17, S18, S22, S23 plus real-database confirmation of S01/S02/S05.

- [x] [YOU] Add opt-in catalog PostgreSQL tests and extend the existing disposable runner to include them. Reuse only needed fixture helpers; keep reset/seed actions confined to the runner-created database and always stop that cluster.
- [x] [YOU] Verify current role changes, expiry/revocation/deactivation, no-publication versus dependency failures, newest-attempt selection despite timestamp/status differences, and safe refresh projection through the production route.
- [x] [YOU] Prove publication and refresh snapshot races with synchronized independent connections. Verify the next request sees committed changes and no request mixes snapshots. Exercise failure during dependency cleanup without sending success.
- [x] [YOU] Run real loopback HTTP persona checks, focused catalog/auth checks and the full offline regression suite. Record runtimes, counts, skips and which tests used real PostgreSQL/HTTP; do not count skipped database tests as passed.

Gate: automated evidence passed: 70 checks in the disposable runner, including 36 database-backed checks; full regression passed 236 offline checks with those 36 opt-in tests skipped and reported separately. This does not prove frontend navigation, preview/SQL execution or live published data.

### Step 5 — Operator check and focused handoff

Scope: R13–R15; S22, S23; preserve S24 as later frontend work.

- [x] [YOU] Extend the existing hidden-input persona checker with optional `--catalog`; preserve its auth-only default and logout behavior. Validate role-filtered catalog responses and post-logout denial without logging credentials, tokens or response bodies; cover both modes with tests.
- [x] [YOU] Update backend/root README, SDD status, NOTES and a unique implementation session with exact commands, measured evidence and remaining limits. Review the final slice diff and documentation links; preserve unrelated work and follow CONTRIBUTING.
- [x] [ME] Run the documented optional catalog persona check with retained local accounts once the API is ready. Passed for all three Docker personas on October 4; see [operator evidence](../../ai/sessions/2026-10-04-catalog-docker-operator-check.md). No command should require copying a token into the terminal or publishing test data.
- [ ] [ME] Review the behavior and give a short explanation of why a failed newest refresh can coexist with `data_ready=true`. Record only the observed response, not inferred understanding.
- [x] [YOU] Close only the supported acceptance claims and provide the handoff. Keep S24/navigation in later frontend work. Commit/push/PR only after an explicit request, using focused changes and retained history.

Gate: implementation diff reviewed by AI; alayala's retained-account operator check passed; his behavior review remains pending. Ongoing data evidence and future UI/query security remain open.

### Scenario coverage

| Scenarios | Planned proof |
|---|---|
| S01–S04 | Steps 2–3 metadata tests and complete role-filtered HTTP bodies; step 4 confirms live session/database integration. |
| S05–S09 | Step 3 denial-before-read and transport tests; step 4 real session/role transitions; step 2 unknown-role policy regression. |
| S10–S15 | Steps 3–4 state/error fixtures, real active pointer, newest sequence and failure-versus-empty-state checks. |
| S16–S20 | Step 4 synchronized database races and wire checks; step 3 canary/no-I/O guards and cleanup failures. |
| S21–S24 | Steps 2–3 malformed registry failure; steps 4–5 regression/real HTTP/operator evidence; S24 explicitly deferred to frontend. |

### Verification commands after implementation

Run from `backend/`. The catalog files and extended runner/checker now exist. Use the existing locked environment; do not alter dependency versions to make a check pass.

```bash
uv run --locked python -m unittest discover -s tests -p 'test_catalog_unit.py' -v
uv run --locked python -m unittest discover -s tests -p 'test_auth_unit.py' -v
uv run --locked python tests/run_local_auth_checks.py
uv run --locked python -m unittest discover -s tests -v
```

The third command now includes auth and catalog tests. It creates a disposable PostgreSQL 17.11 cluster using the existing `TRINITY_PG_BIN` mechanism. Do not point reset fixtures at a retained database. The fourth command runs all offline tests; opt-in database skips are reported separately from the third command's evidence. Stop on failure and correct the focused cause before broad reruns.

The later evaluator-owned command, with the API and retained accounts already configured, is:

```bash
uv run --locked python -m trinity.auth.check --catalog
```

At the design stage these commands had not run. Implementation verification used the existing `.venv/bin/python` equivalents because uv was absent from the agent PATH; every installed direct dependency matched its pin. The catalog flag is implemented and tested. This is not a fresh locked-install result. No formatter, linter or type checker is configured in the inspected `pyproject.toml`; use the project's test workflow and `git diff --check`, and recheck configuration at implementation time.

### Current checkpoint

Done: catalog implementation, offline regression, disposable PostgreSQL/HTTP acceptance, and retained-account Docker operator check.
Pending: alayala's behavior review; S24 belongs to later frontend work.
Blocker: none for the catalog operator check; all three personas passed on the running Docker API.

Next: [ME] explain why a failed newest refresh can coexist with `data_ready=true` in the separate behavior review.
