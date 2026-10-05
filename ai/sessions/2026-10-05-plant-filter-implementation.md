# Plant and generator choices — implementation and delivery

## Objective and authorization

[ME] Alayala requested completion of the Plant filter slice directly, without a new SDD process. He then authorized commit, push and merge into `pending-endpoints-frontend`. This supersedes the old proposal's planning-only boundary for this slice. [YOU] implemented the endpoints on `feat/plant-filter-endpoints`, based on the integrated dashboard/recovery branch. No new SDD artifact was created.

## Behavior and contributions

[ME] Authorized proceeding after the recommendation to search exact Plant IDs and displayed latest names. [YOU] implemented literal Unicode case-folded substring comparison without Unicode normalization or wildcard expansion. A16 records that refinement. The implementation uses binary ascending name order to resolve same-date name conflicts; this is an AI-selected deterministic implementation detail, not a separate human decision.

`ChoiceService.prepare` authenticates and authorizes the dataset, parses primitive input, commits one shared analytical rate debit, validates semantics/cursor, reauthorizes and pins the active publication, then reserves the existing SQL/preview capacity. `QueryExecution.execute` stages only checksum-verified files for the permitted dataset, executes a typed `ChoiceOperation` in the existing network-disabled container and validates its bound response. It reports success only after owned container/staging cleanup.

`execute_choices` computes distinct options across the full requested range. Facility labels use the latest non-null observation, then binary ascending label order for same-date ties. Only the selected label participates in name search. Generator choices require an exact facility ID. Exact IDs, case and leading zeros are retained. Choice cursors use a separate `ch1` envelope and bind dataset, route, publication/version, effective dates, parent/search, page size and last ID. A new publication returns `409 publication_changed`; a changed request or wrong-purpose token returns `422 invalid_cursor`.

These routes reuse `enable_preview` and the configured cursor key ring. Deployment defaults stay disabled. No live EIA/S3 call, retained data mutation, migration or dependency addition is part of this delivery. All data used for the new tests is synthetic; FINDINGS remains unchanged and data evidence remains ongoing.

## Checks and corrections

| Check | Measured result |
|---|---|
| Focused choice/service/health checks before integration | 24 passed, no skips. |
| Shared PostgreSQL/HTTP/container regression before schedule integration (`run_local_sql_checks.py --all`) | 128 passed, zero skips; SQL, preview, choice, auth, catalog and national checks, including cleanup/crash probes. |
| Full offline regression after schedule integration | 790 discovered, 532 passed, 258 opt-in skips, zero failures/errors. |
| Choice acceptance after integration (`run_local_sql_checks.py --choices`) | 27 passed, zero skips, with the rebuilt matching query image. |
| Auth/catalog/settings acceptance after integration (`run_local_auth_checks.py`) | 112 passed, zero skips, in disposable PostgreSQL 17.11. |

The initial five container choice checks also passed independently. Fixtures use
real producer Parquet/manifest bytes and synthetic object storage, not AWS.
The locked query image built successfully from `backend/Dockerfile.query`;
the final image is `sha256:239c5630a752bdc8ad50cd709287eee68409a0ad2d9f69a8c322cc3ff354a448`.
Native checks use the existing sibling Python 3.14.8 environment with this
worktree's `backend/src` and `backend/tests` on `PYTHONPATH`; they are not a fresh
native installation. The runners use private disposable database clusters.

Diff whitespace checks and local file-link checks passed; `docs/openapi.json`
parsed successfully. No formatter/linter dependency was added. Tests are the
repository's unittest runners.

The first HTTP test exposed the missing exact-route registration in `SafeTransport`; the new routes now defer their primitive input checks until after identity checks, while retaining transport size limits. The first full offline run exposed the expected health route-set update. Both were corrected and their checks rerun. Review also changed cursor payload encoding to canonical UTF-8 so maximum-length supplementary Unicode IDs/search remain within the 4096-character limit, and added a runtime output-size regression. Existing Starlette/httpx deprecation warnings remain; no dependency was changed.

## Integration and Git delivery

[YOU] Kept implementation/tests (`ca91ab8`) separate from behavior/evidence
(`348e4f5`). While this slice was being checked, schedule settings reached
`pending-endpoints-frontend` at `c93c41d`. Integrated that target without squashing.
The sole conflict was `create_app`'s signature: preserve both `settings_service`
and `choice_service`, plus their application state. The diff against the updated
target contains no change to settings, refresh or worker implementation. The
post-integration checks above verify the combined application.

[ME] Authorized pushing the feature and merging into `pending-endpoints-frontend`.
The final delivery preserves both histories and uses a merge commit. Git refs
and history provide the final delivery identity; this record does not claim a
retained deployment or a frontend run.

## Remaining boundary

Frontend clicks and retained deployment/publication acceptance are separate from this backend delivery. No new EIA findings or retained-runtime success is claimed. Next action: [ME] use the delivered endpoints in the frontend integration.
