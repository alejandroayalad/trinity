# Catalog and permissions — design and tasks

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`
Inspected base: `fde733b`, with existing working changes preserved.
Status: Specification approved; design and tasks drafted; no implementation.

## Objective and authorization

[ME] Alayala requested “continue with design and tasks, approve it” after receiving the specification and its explicit proposed newest-attempt freshness detail. This approves the specification, including D01, and authorizes design/task drafting. It does not request implementation, runtime commands or Git delivery.

[YOU] AI recorded D01 under A16, clarified the API prose without changing its response schema, marked proposal/specification status, and drafted [design](../../sdd/catalog-permissions/design.md) and [tasks](../../sdd/catalog-permissions/tasks.md). Updated the README index and NOTES. Prior proposed wording remains in the earlier session records rather than being treated as an accepted choice retroactively.

## Evidence and design choices

AI read the current SDD and applicable decisions/contracts, existing local-auth design/tasks, CONTRIBUTING, status, current router/service/permission/publication/refresh code, database adapter, response models, migration fields, auth test fixtures, disposable runner, operator check and dependency configuration.

The current application has one reusable authenticated read-only transaction, a shared dataset policy, canonical Arrow definitions and an active-publication reader. Catalog is still absent. The design adds the A15 catalog feature, a safe three-field refresh summary and router registration. It extracts the existing permitted-key rule for reuse, preserving all capabilities. No additional production dependency, migration, engine, cloud fetch or new role policy is planned.

D01 now means greatest `run_seq`, regardless of completion status; the active publication still determines readiness and publication dates. The fixed read needs no input interpolation or candidate join. Persisted-value failures map to dependency errors, while malformed static definitions remain internal errors. Snapshot tests use synchronized connections, with real HTTP/persona evidence separate from offline doubles.

The existing disposable runner currently discovers `test_auth*.py`, and the current persona command has no `--catalog`. Their extensions are explicit future tasks; merely running the current commands would not prove catalog acceptance. Keep existing auth behavior valid. Tests may reuse a small fixture extraction but must not duplicate all auth tests through TestCase inheritance.

## Verification and preservation

The design/task request changed documentation only. This task did not edit source, tests, findings, live evidence, dependencies or the OpenAPI schema. No application test, migration, database write, account provisioning, browser action, build, container or EIA/S3 request ran. No commit, push or PR was created.

A start-of-turn hash comparison detected concurrent changes to `connector/normalize.py`, `test_normalize.py`, `test_parquet.py`, FINDINGS and backend README; the source/test/finding paths no longer appear dirty in the final status. These changes were not made or reverted by this task, and their previous work was not restored over the new state. The inspected HEAD and working branch stayed `fde733b` and `feat/catalog-permissions`. Recheck status before implementation instead of assuming the initial unrelated patch remains in this worktree.

Passed: 24 newly introduced local links/anchors, balanced fences, edited-line whitespace and `git diff --check`. Verified R01–R15 and S01–S24 remain unique and sequential, all 24 scenarios are mapped to tasks, the plan has five numbered stages starting with the ongoing evidence duty, and only the completed specification-approval item is checked. Reviewed new artifacts and the focused documentation diffs. Of 61 start-of-turn preservation hashes, 56 stayed identical; the five concurrent changes are listed above. Dependency pins, lockfile and OpenAPI bytes remained unchanged. Concurrent removal of live-preparation prose from README/NOTES was also left intact; this task's README edit is only the catalog SDD index row.

These are documentation checks, not schema-runtime, PostgreSQL, HTTP or frontend acceptance. Future commands in tasks are instructions for implementation validation, not results.

## Current checkpoint

Done: specification/D01 approved and recorded; design and task plan drafted.
Pending: design/task review and implementation authorization; all catalog runtime acceptance.
Blocker: none for review. The shared worktree changed concurrently; inspect current file scope before implementation or Git delivery.

Next: [ME] review the design's Human section and authorize the desired implementation stage.

## Subsequent implementation authorization

[ME] Alayala requested implementation and reserved the local operator check for himself. This supersedes the implementation-pending checkpoint above. [YOU] AI completed the backend slice and recorded offline versus real database/HTTP results in the [implementation session](2026-10-04-catalog-permissions-implementation.md). The retained-account operator check and user behavior review remain pending; no Git delivery was authorized.
