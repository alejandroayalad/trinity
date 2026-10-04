# Catalog review and focused delivery

Date: 2026-10-04. Decisions: A9, A15–A17, A19–A21.

## Objective and contributions

[ME] Alayala requested a catalog review, grouping sessions by theme, the new organization, and commit/push. He explicitly selected the full catalog slice, including implementation and tests, when asked to distinguish SDD-only from full delivery. No merge or PR was requested.

[YOU] Inspected the dirty source checkout, accepted catalog SDD, canonical permissions/metadata, implementation, tests and operator records. Created `feat/catalog-permissions-delivery` from current `origin/main` (`285baa1`) in a separate worktree. Copied only the catalog changes and required fixture refactor, preserving newer merged Docker/live-data work. SQL commits, SQL migration tables and preview changes are excluded. No existing branch history was rewritten.

## Review result

No blocking defect was found in the reviewed catalog paths. This is a bounded review of the current source and executed tests, not proof that all possible defects are absent.

| Expected behavior | Inspected flow and evidence |
|---|---|
| Viewer receives national metadata only; Analyst/Admin receive all three definitions. | `catalog.router.catalog` uses `require_capability`; `get_catalog` calls `permitted_dataset_keys` before catalog-state reads. Role filtering occurs before registry construction. Persona and stored-role-change tests inspect complete responses. |
| One response uses one current identity/publication/refresh snapshot. | The authenticated dependency supplies one read-only repeatable-read connection. `get_catalog` reads the active publication once and `read_last_refresh` selects greatest `run_seq` through that same connection. Synchronized independent-connection tests change publication/refresh during a request. |
| A newer failed refresh does not hide an existing publication. | Readiness and published dates come from `read_publication`; the separate three-field refresh projection reports the newest attempt. Failure fixtures preserve `data_ready=true` and omit error/candidate/actor details. Missing or inconsistent state fails safely instead of returning a fabricated empty catalog. |
| Catalog does not access outage files or analytical execution. | `registry.describe_dataset` uses canonical `DATASETS` metadata. The route reads PostgreSQL application metadata only. No-I/O guards cover source/storage/engine/container entry points. |
| Existing auth behavior remains intact. | Shared fixture extraction retains auth test bodies, and the disposable runner includes existing auth plus catalog checks. The route inventory adds only `/api/v1/catalog`. |

The source checkout's 16 catalog unit checks passed before assembly. Final delivery-worktree checks are recorded below after they finish. The prior retained-account Docker check is historical evidence for all three personas with no active publication; it was not rerun here. See the [operator record](2026-10-04-catalog-docker-operator-check.md).

## Organization and scope

- `sdd/catalog-permissions/README.md`: entry point and reading order for proposal → specification → design → tasks → evidence.
- `ai/sessions/README.md`: one thematic index for catalog, authentication, data evidence, connector/storage, architecture/contracts, SQL scope and delivery practices. Existing dated session files are retained unchanged in place.
- Root/backend READMEs: runtime setup and feature entry points; `DECISIONS.md` remains authoritative for accepted decisions.

No source-data findings changed. No credentials, retained database, account, cloud resource or deployment was modified. Tests use synthetic identities and disposable state. Viewer Catalog/SQL navigation hiding and direct-screen denial remain later frontend work. Alayala's explanation of the publication-versus-refresh distinction remains unobserved; this review does not claim it.

## Current verification

All commands used the existing locked CPython environment from the original checkout, with `PYTHONPATH` explicitly set to this delivery worktree's `backend/src`. No package installation or dependency changes were made. This validates this branch's sources rather than its neighbor's editable installation.

| Check on the delivery worktree | Result |
|---|---|
| `python -m unittest discover -s backend/tests -p 'test_catalog_unit.py' -v` | 16 passed, 0.860 seconds. |
| `python -m unittest discover -s backend/tests -v` | 275 discovered; 239 passed and 36 opt-in database tests skipped, 47.377 seconds. |
| `python backend/tests/run_local_auth_checks.py` | 70 passed without skips, 78.929 seconds: 36 real PostgreSQL checks and 34 offline auth/catalog checks. Includes real loopback HTTP for all personas in both publication states. |
| Documentation | 357 local Markdown links/anchors checked before commits; balanced code fences and `git diff --check` passed. |
| Scope | No changes to connector/query code, migrations, dependency/lock files, canonical OpenAPI or FINDINGS relative to current main. |

The initial mixed source checkout also passed its 70-check runner (69.852 seconds). Delivery acceptance above is the relevant publication evidence. Starlette emits an existing httpx deprecation warning; dependencies were not changed to suppress it. No separate formatter/linter/type checker is configured in the repository's pyproject.toml.

`1f0046f` commits the complete catalog implementation, SDD, original evidence and handoff. A second documentation commit adds the thematic index, SDD entry point and this fresh review. The requested push targets only `feat/catalog-permissions-delivery`; it does not merge into main or publish the separate SQL history.

Done: bounded review, catalog acceptance, focused implementation commit and session organization.
Pending: later frontend navigation and the separate human behavior review.
Blocker: none found for this delivery.
Next: [ME] open the catalog SDD entry page and review the delivered branch.
