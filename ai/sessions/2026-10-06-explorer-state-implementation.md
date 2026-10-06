# Explorer state implementation and verification

## Objective and contributions

[ME] Alayala authorized implementation and verification of original-report QA-02,
QA-04, QA-05, QA-08 and QA-06 (analytical pages only). [YOU] Codex traced current
code/contracts, wrote the [bounded SDD](../../sdd/explorer-state/spec.md), implemented
frontend state fixes, and ran the checks below. No human understanding or visual
acceptance is claimed. A9/A16/A19/A20/A26 remain unchanged.

The supplied `frontend/test-results/live-qa-2026-10-06/REPORT.md` was absent:
`cat` returned no such file; `ls frontend/test-results` showed only the earlier
Viewer test failure directory; `find ../ -path '*/live-qa-2026-10-06/REPORT.md'`
returned no paths. Issue mapping comes from the current user prompt. The historical
`sdd/qa-01-request-handling` name does not identify the original QA-01 logout issue.

## Root causes and corrections

### QA-02 — partial: frontend fixed; live capacity/network verification open

- Severity and scope: moderate, existing frontend behavior; correction uncommitted.
- Expected: only settled facility terms execute; superseded reads cannot win.
- Observed before: `FacilityChoices` used raw input in its query key. Each edit
  started a read. Dashboard dependent reads could continue during range changes.
- Evidence: `FacilityChoices` in `frontend/src/pages/catalog/Choices.tsx` now
  detaches each obsolete draft key immediately and enables the new query after
  300 ms. `DashboardData`/`Contributions` in
  `frontend/src/pages/dashboard/Dashboard.tsx` use disabled observers during
  range loading, preserving prior display and consuming existing AbortSignals.
- Failure scenario: type `o`, `ol`, `old`; each formerly executed. The regression
  now records only `old`, then `latest`; resolving the old promise cannot replace
  the latest choices. Initial focus can still request the unfiltered list.
- Recommended correction: implemented debounce and query coordination, with lazy
  generators and publication-bound contribution reuse. No limits/retry increases.
- Validation still required: live request/abort/429 counts and proof that backend
  execution stopped before admission capacity was released.

### QA-04 — fixed within the verified frontend slice

- Severity and scope: moderate, dashboard state presentation; correction uncommitted.
- Expected: the selected range is clearly loading until its data arrives.
- Observed before: `Dashboard` used `placeholderData` but only displayed initial
  `isPending`. An old chart looked like the selected range's completed result.
- Evidence: `Dashboard` now renders a persistent polite status and `aria-busy`
  region. Old data is explicitly labeled previous/updating. Tests control delayed
  replies, failure, Retry, and final completion; live rapid presets also completed.
- Failure scenario: select 1y, 90d, then 30d while replies are pending. Previous
  data remains labeled and late replies cannot replace the final selection.
- Recommended correction: implemented status, preserved content and current retry.
- Validation still required: [ME] screen-reader and visual acceptance; no human
  assistive-technology walkthrough was performed.

### QA-05 — fixed within the verified frontend slice

- Severity and scope: moderate, preview pagination; correction uncommitted.
- Expected: an explicit changed filter starts a new first-page visit.
- Observed before: `DatasetTable` keyed infinite queries only by filters. Returning
  to a previously paginated filter reattached its cached page/cursor chain.
- Evidence: `DatasetTable` in `frontend/src/pages/catalog/TableView.tsx` adds a
  component/visit identity to the existing query key, cancels obsolete work and
  clears Load all. Saved per-dataset filters and other cache entries remain intact.
- Failure scenario: paginate A, start Load all, select B, return to A. Controlled
  tests now record no replay after the new first page. Live 2000 rows → facility
  filter → Reset returned to 1000 rows. Publication restart tests still pass;
  mixed publications are not rendered and cannot continue Load all.
- Recommended correction: implemented per-visit cursor ownership and cancellation.
- Validation still required: [ME] retained browser-history acceptance.

### QA-08 — fixed within the verified frontend slice

- Severity and scope: moderate, filter state; correction uncommitted.
- Expected: Reset clears draft/applied dates, IDs, search, and pagination.
- Observed before: `resetFilters` cleared dates/filters but could not clear the
  independent `FacilityChoices.search` state.
- Evidence: Reset remounts choice controls and invalidates their timers/observers.
  Date changes also close/restart choices. Changing facility clears generator.
  Explicit linked facility and generator strings preserve leading zeros through
  fallback options and preview requests. A never-opened list sends no request.
- Failure scenario: Reset during debounce or an in-flight search. Both tests
  prove no old term/option returns. Live Reset cleared `Palo` and facility `6008`.
- Recommended correction: implemented one Reset boundary for all local states.
- Validation still required: [ME] acceptance of controls closing on date changes.

### QA-06 — fixed for analytical recovery only

- Severity and scope: moderate, analytical error controls; correction uncommitted.
- Expected: Retry uses current parameters, honors Retry-After, and is single-flight.
- Observed before: `PageError` offered immediate Retry without a busy guard or
  server-wait gate. Callers used cancel-and-refetch behavior on repeated clicks.
- Evidence: `PageError`/`ReadRetry` in `frontend/src/pages/shared.tsx` gate the
  button with a synchronous latch, pending state and server wait. Analytical
  callers return `refetch({ cancelRefetch: false })`. Forbidden/unavailable remain
  separate. Contributions/sparks recover publication changes through Dashboard.
  Choice/preview continuation failures restart; first-page publication failures
  remain manual rather than creating restart loops.
- Failure scenario: repeated Retry while a promise is unresolved previously could
  restart work; controlled tests prove one operation. Exhausted short 429 retry
  makes exactly two requests. The existing `api/retry.ts` policy is unchanged.
- Recommended correction: implemented current-query recovery; no Admin mutation
  behavior changed. Dashboard metric failures now also expose read recovery.
- Validation still required: live transient-backend failure recovery; injected
  browser failures are simulated and establish no backend behavior.

## Files and boundaries

Implementation: `frontend/src/pages/dashboard/Dashboard.tsx`,
`frontend/src/pages/catalog/TableView.tsx`, `frontend/src/pages/catalog/Choices.tsx`,
`frontend/src/pages/shared.tsx`. Existing endpoint signal propagation and automatic
retry policy were inspected and reused without changing their files.

Tests: new `frontend/src/pages/explorer-state.test.tsx`,
`frontend/tests/e2e/explorer-state.spec.ts`, `frontend/tests/e2e/explorer.config.ts`;
updated `frontend/src/pages/qa01.test.tsx` and `frontend/src/pages/pages.test.tsx`
for the server wait and lazy generator/publication restart behavior.

No dependencies, auth, roles, SQL, API schemas, backend implementation, retained
settings, refreshes, candidates or publications were changed. Backend cache work
was present initially and changed concurrently; it was not edited or reverted.
No commit, push, PR, or build was performed.

## Checks actually run

- `npm run typecheck` from `frontend/`: passed.
- `npm run lint` from `frontend/`: passed, zero warnings.
- `npm test` from `frontend/`: 100 tests passed in 11 files.
- `npx playwright test --config tests/e2e/explorer.config.ts`: 2 passed against
  the running Vite application, with fully simulated API transport.
- `git diff --check`: passed; implementation/test diff reviewed.
- Earlier checks caught test selector/timer/provider errors and a TypeScript
  query-inference error. Those were corrected before the passing final runs.
  Two initial npm invocations from the repository root failed because package.json
  lives in frontend; no such failed invocation is counted as verification.
- Build not run: AGENTS.md assigns builds and evaluator acceptance to [ME].

## Browser/network evidence

Live browser used the existing signed-in session, without reading/exporting its
credentials. Publication/version display: `687c1006-24e9-47fc-8a7d-1cb05961a5c1`,
latest observation `2026-10-05`, published display October 6 at 00:58 UTC.
These values were read from the current UI, not from an older publication fixture.

- Rapid 1y → 90d → 30d: previous/updating status appeared; completion status
  subsequently appeared with 30d selected. No captured console warnings/errors.
- Generator table loaded 1000 rows, Load more reached 2000. Search `Palo` returned
  current choice `Palo Verde (6008)`. Selecting it returned 90 rows.
- Reset cleared the search/facility and returned to 1000 rows, not cached 2000.
- Direct `/catalog/generator_outages?facility=6008` kept exact ID visible and
  returned 90 rows. Generator list remained unopened until focus, then showed
  current generators `1`, `2`, `3`. No captured console warnings/errors.
- Live request counts, cancellations and 429 counts were not instrumented through
  the connected browser. The automated credentials were not configured, so no
  separate authenticated Playwright session was created. No backend capacity
  release claim follows from these UI observations.

Simulated Playwright evidence is stored separately under
`frontend/test-results/explorer-state-2026-10-06/`: `results.json` includes network
attachments; test subdirectories contain dashboard recovery and Catalog Reset
screenshots. No traces/video or credential captures were enabled. Original QA
artifacts were not deleted. Synthetic dates/IDs in tests are not EIA evidence.

Final recorded simulated network: six dashboard requests (including two initial
30d calls under development StrictMode); two browser cancellations (initial 30d
and obsolete 1y); two injected 429 responses; one explicit 90d recovery request;
zero unexpected console errors. Catalog recorded six preview calls (including
initial StrictMode duplication), only one cursor continuation, two facility reads
(initial focus plus settled `Synthetic`), and no generator request. No intermediate
search terms executed. Simulated 429 console resource messages were expected and
excluded from the unexpected-error assertion. No live backend failure was induced.

## Checkpoint and next action

Done: bounded implementation, automated regressions and live state checks.
Pending: [ME] build and human acceptance; live network/capacity evidence for QA-02.
Blocker: original report unavailable; full original-report closure cannot be claimed.

[ME] Next: from `frontend/`, run `npm run build`.

## Delivery authorization

[ME] Alayala subsequently requested commit and push of this slice. [YOU] Created
implementation/test commit `6c9e780`; the SDD and verification record are delivered
in a separate documentation commit. Unrelated working-tree changes stay excluded.
The build and live-capacity verification gaps above remain unchanged.
