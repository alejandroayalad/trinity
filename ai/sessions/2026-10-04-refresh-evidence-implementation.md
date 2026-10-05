# Refresh evidence implementation and Preview reconciliation

Date: October 4, 2026 (America/Merida).
Branch: `feat/refresh-publication`.
Implementation baseline: `aea1eda` (merged catalog/SQL/Preview).
Status: initial persistence and verified registration boundary implemented; full Refresh pending.

## Objective and contributions

[ME] Alayala reported two defects in the uncommitted integration plan: duplicate
evidence naming incompatible with Preview, and a migration plan based on 0002 instead
of the completed 0004 head. He requested both corrections and then implementation.
[YOU] AI confirmed `read_preview_publication` and `0004_preview_evidence` in the
completed feature checkout and the locally available merged main. AI advanced the
branch by fast-forward without creating a commit. The draft documents were preserved;
one NOTES content conflict was resolved by retaining both histories. No remote Git
operation occurred.

## Changes and decision references

A22 records implemented choices; A9/A16/A19/A20/A21 remain authoritative. The
[contract](../../sdd/refresh-publication/integration-contract.md), [design](../../sdd/refresh-publication/design.md)
and [tasks](../../sdd/refresh-publication/tasks.md) now identify the Preview baseline.

`0005_refresh_evidence` follows `0004_preview_evidence`; `0006_refresh_dispatch`
follows 0005. They add artifact/result records, receipt/summary identities, outbox/
command tables and future worker ownership/deadline columns. They preserve existing
Preview rows and do not backfill guessed receipts. New receipt-bearing candidates
have selected-step binding and immutable evidence enforcement. Existing records
without writer receipts remain under the prior constraints, not retroactively verified.

`refresh.evidence.load_candidate` requires the trusted original receipt hash, parent
completion and matching typed validation/storage evidence. Existing local/remote
verifiers check every bundle member. `CandidateRegistration.register` checks current
run/slot/fence before reads and before commit, and uses Preview's existing
`evidence_bundle_sha256` and `validation_attempt_id`. The connector attempt binds
to the same-run selected validation step; it is not the database step UUID.

The registration transaction writes analytical artifacts, 16 required checks and 23
diagnostics, frozen identities and either review state or publication intent.
It releases the preparation lease, retains admission, and never changes the active
publication. Exact completion replay has no duplicate effects. No public writer
endpoint, dispatcher, supervisor or publisher was added in this first boundary.

## Verification actually run

Commands ran from `backend/` with `PYTHONPATH=src`, using the existing sibling
checkout's Python 3.14 environment. No dependency installation or build occurred.
The repository-form commands are documented in `backend/README.md`.

| Check | Observed result |
|---|---|
| `python -m unittest discover -s tests -p test_refresh_evidence.py -v` | 5 passed. Reconstructed exact reports/receipts; rejected child-only, wrong hash, changed local/remote bytes and contradictory failure evidence. |
| `python tests/run_local_sql_checks.py --refresh --failfast` | 9 passed after final ownership/lease checks, in 5.513 seconds. PostgreSQL 17.11 disposable Unix-socket cluster, cleaned by runner. |
| `python -m unittest discover -s tests -q` | 452 collected, 368 passed, 84 opt-in checks skipped; 39.232 seconds. |
| `python tests/run_local_sql_checks.py --all --failfast` | 72 collected, 55 passed, 17 query-image-dependent checks skipped; 85.670 seconds. Existing SQL/Preview/auth/catalog regression in disposable PostgreSQL. |

The new database checks include clean migration startup, upgrade from 0004 preserving
every existing candidate field, one Alembic head, wrong attempt/stale fence rejection,
transaction rollback, deferred commit failure and immutable accepted identities.
A final review tightened outbox lease completeness and denied expired/unclaimed
workers before evidence reads; both new regressions passed. The broader suites above
ran before those final narrow guard changes; the focused nine-case database suite
ran afterward. Both warning-bearing and warning-free routing were exercised; duplicate registration
created only one outbox obligation.

Compatibility check: new writer → explicit test-only publication effect → actual
`PreviewService.execute` → production `read_preview_diagnostics`. The test executor
checks provenance and returns its pinned evidence; it does not execute query containers
or represent the future publisher. No candidate evidence fields are rewritten by
the publication fixture to conceal a mapping error. Full writer → production publisher
→ container Preview remains a later acceptance boundary.

The first broad database run failed because `test_sql_postgres` had its own old
TRUNCATE table list. AI added the four new dependent tables to both disposable reset
lists and reran the suite successfully. No CASCADE shortcut or weakened constraint
was used. Existing Starlette/HTTPX deprecation warnings remain. An initial relative
venv invocation emitted interpreter-prefix warnings; later checks used the existing
interpreter's resolved path and this worktree's source via PYTHONPATH.

Static checks passed for 23 changed/new files: Python AST parsing, whitespace and
395 local Markdown link targets. The diff and new files were reviewed. Link checks
did not verify external URLs or heading fragments.

## Remaining work and limits

Admin admission and tracking routes, full-refresh dispatch/recovery, latest-national
discovery, supervised worker progress, incomplete/failed evidence import and production
publication are not implemented here. Setup writes and review/recovery commands remain
product dependencies. Full worker budgets in the design remain proposals; columns
alone do not enforce execution deadlines. Continued coding is already authorized.

No retained-database migration, live EIA/S3 call, Redis call, query-image build,
commit, push or PR occurred. Tests used synthetic source/storage and disposable SQL.
Maintain data evidence — ongoing; these fixtures are not new EIA anomaly findings.

Done: both plan corrections, linear migrations and verified successful-candidate writer.
Pending: remaining Refresh tasks and production publisher/Preview execution acceptance.
Blocker: none for continued authorized implementation.

Next: [YOU] implement Admin admission and atomic slot/run/outbox acceptance.
