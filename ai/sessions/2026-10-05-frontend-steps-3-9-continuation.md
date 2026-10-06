# Frontend steps 3–9 — implementation and measured checks

Date: October 5, 2026. Checkout: `trinity-main`, branch `frontend`, starting
HEAD `d321ff3`. This record continues the [scaffold session](2026-10-05-frontend-implementation.md)
and [task checklist](../../sdd/frontend/tasks.md). Changes were initially local and
uncommitted; the subsequent Git delivery authorization is recorded below.

## Objective and contributions

[ME] Alayala asked to continue and finish steps 3–9. [YOU] Codex implemented the
session/shell, Catalog and tables, SQL Explorer, Refresh/candidate review,
national dashboard, Settings/setup, entity choices and failed-run recovery.
Codex added their missing backend routes, scheduler role and automated checks.
The [bounded design note](../../sdd/frontend/design.md#continuation-design--steps-79)
records the implementation assumptions. The continuation covers these steps;
it does not establish human approval of visual output or authorize live activation.

Alayala's original Figma layouts, the ChatGPT brand and earlier Claude work stay
distinct. This continuation is Codex work. Canonical attribution remains in
[NOTES](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026) and A25.
No historical session was rewritten. No dependency version, contract field,
database migration, retained account, retained publication or remote resource changed.

## Input, flow and output

The browser stores the server session in `sessionStorage`, verifies `/me`, and
uses its capabilities for navigation and route guards. All data comes through
relative API paths. Session loss clears private caches. A changed publication
invalidates analytical queries; pages refuse to combine different publications.
An explicit facility link takes precedence over filters kept from a prior visit.

National and choice reads specialize the existing `PreviewService` admission,
authorization, pinned publication, authorized mount and supervised cleanup.
DataFusion executes choices inside the network-disabled query container, with
bounded returned pages. Exact source IDs and decimal strings survive the flow.
Dashboard gaps are display calendar points, not invented zero-valued source rows.
Zero capacity produces an unavailable share and remains distinct from missing data.
Viewer execution mounts only national data.

Settings writes use the lifecycle lock, current Admin authority and revision
compare-and-swap. Initial setup time is retained across later edits. Saving does
not start work. The scheduler admits future due occurrences through the existing
outbox, skips missed or blocked occurrences and deduplicates the same occurrence.
It is a new explicit worker role; it was not enabled on the retained system.

Recovery checks current authority, command replay, target revision and durable
writer-stop evidence before resolving a warning or replacing a failed run.
It retains history and the active publication. Same-candidate publication retry
still rejects permanent integrity failure. Full rerun or warning resolution can
be allowed once the failed writer is proven stopped.

Failure examples: a stale settings/candidate ETag reloads current data rather
than overwriting another Admin's work; a revoked session returns to sign-in;
an unknown worker stop state rejects recovery; a page cursor from an older
publication cannot join the current table.

## Verification actually run

| Check | Observed result | Evidence boundary |
|---|---|---|
| Node 24.21.0 `typecheck`, `lint`, `test`, `build` | Passed; 69 tests in 9 files; bundle check passed | Offline helpers/components and production compilation |
| Python full discovery | 567 discovered; 382 passed, 185 skipped | Existing installed Python environment; opt-in service tests skipped |
| `run_local_auth_checks.py --frontend` | 7 passed | Native disposable PostgreSQL 17.11 and real HTTP adapters; settings CAS, one-time setup, malformed JSON, access, recovery replay/stop proof, scheduler admission |
| `run_local_sql_checks.py --pattern test_frontend_runtime.py` | 2 passed | Real disposable PostgreSQL and Docker execution; national/metric values, role isolation, signed choice continuation, changed-publication rejection and cleanup |
| `run_local_auth_checks.py --frontend-browser` | 5 passed | Real Chromium, loopback HTTP and native disposable PostgreSQL; all personas, guards, no-publication states, logout/revocation, setup and refresh polling |
| `run_local_auth_checks.py --frontend-data` | 3 passed | Real browser and isolated Docker over synthetic published Parquet; dashboard gaps/ranges/keyboard/reduced motion, Viewer detail exclusion, Analyst choices/tables/SQL, real rate limiting |
| Publication regression | Focused 18/18 passed | Disposable PostgreSQL; includes stopped integrity-failure recovery availability |
| Broader Refresh/publication runner | 93 discovered: 83 passed, 9 skipped, 1 obsolete assertion failed on the first run | Corrected the assertion to reflect the new full recovery actions; the focused 18-test publication suite then passed. The whole 93-test command was not rerun |

Commands used the existing sibling Python environment with `PYTHONPATH=backend/src:backend/tests`.
Frontend checks used the official Node 24.21.0 archive after SHA-256 verification,
without replacing the system Node. The query image was built from the existing
locked Dockerfile; Docker reported immutable ID
`sha256:ae9a4f09e025098c6db53d3b33bbde26ac1b05b203ef97a6cfe2cdde68450cac`.
This does not establish a fresh locked install of the complete backend.

Playwright did not replace `fetch`. Its data fixture replaces object storage
with synthetic objects while using production admission, HTTP and actual query
containers. The no-publication refresh ended in **requested** and was polled
more than once. No preparation worker or EIA request ran in that test.
Settings save and run admission are not successful-refresh evidence.

Accessibility checks found no axe violations on the exercised waiting/setup,
Viewer daily-values and Analyst SQL screens. Browser tests use 1440px/924px
viewports and keyboard drawer controls. This is not an all-page accessibility
audit. Codex inspected a generated dashboard screenshot; no human visual
comparison or design approval is claimed.

Review corrections included quoted mixed-case DataFusion column names, allowed
GET parameter routing, recovery receipt enums, focusable scrollable result tables,
exact ETag reload behavior, zero-capacity comparison copy, mixed-publication
generator rejection, explicit-link filter precedence, chart date/value-domain
animation and reduced-motion handling. Regression tests cover the behavior they
can measure. Python emitted an existing Starlette/httpx deprecation warning;
Node emitted a test-runner color-environment warning. Neither failed checks.

Final review also fixed the startup revocation race: a rejected `/me` promise
can no longer replace the sign-in screen after its session was cleared. The
regression now requires the Account input to appear. All 69 frontend tests and
typecheck/lint/build passed after this fix. `git diff --check`, local Markdown
file-link checks and a changed-file credential-pattern scan passed. Pattern
matching is a bounded check, not a guarantee that every possible secret is absent.

## Gates and remaining evidence

Done: steps 3–9 implementation and the automated checks listed above.
Pending: step 10, alayala's visual/persona review, and unexecuted acceptance scenarios.
Blocker: no code/build failure remains; full acceptance cannot be claimed from these checks alone.

The checklist leaves combined acceptance rows open where only part ran. In
particular, browser candidate approval through actual publication, browser discard
and recovery transitions, multi-page table S12/S13 against changing real publication,
all SQL outcome variants in the browser, and every-page visual/accessibility
comparison remain unverified. Some backend paths have existing service regression
coverage; that is not a substitute for the missing complete browser scenario.
These are acceptance gaps, not reported runtime defects.

No EIA key was used, no retained Compose service was changed, and the default
query-execution gate remains unchanged. Maintain data evidence — ongoing:
synthetic rows here establish no new EIA anomaly or completeness claim.

Next action: open the local UI using the [frontend instructions](../../frontend/README.md)
and compare one persona screen with the retained handoff.

## Subsequent Git delivery authorization

[ME] Asked to push the branch. [YOU] checked the `frontend` worktree, current
remote branch and changed-file scope, then grouped delivery into backend,
frontend and evidence commits. The existing scaffold commits are included in
the branch push. This authorizes Git delivery only; the acceptance and retained
runtime boundaries above remain unchanged. No merge or pull request was requested.
