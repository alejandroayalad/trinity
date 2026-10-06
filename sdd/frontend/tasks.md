# Tasks: Trinity web frontend

Date: 2026-10-05
Status: Implementation authorized on October 5, 2026. Alayala asked Claude to complete steps 1–10 in order, autonomously, and to commit each slice. Unchecked tasks are not evidence of work. Current continuation: alayala requested steps 3–9; Codex implemented them locally. Alayala subsequently authorized a branch push; delivery uses focused backend, frontend and evidence commits. Full acceptance remains open.
Branch: `frontend`, continuation starts at HEAD `d321ff3` (scaffold complete).
Basis: [specification](spec.md), [design](design.md), A17, A25, A26 and the [session record](../../ai/sessions/2026-10-04-frontend-plan-and-spec.md).

## Human

The work has ten steps. Steps 2–6 use backend endpoints that already exist. Steps 7–9 each add one missing backend part and then its page. Step 10 checks the whole app against the handoff.

Rules for every step:

- Start a step only when alayala asks for it.
- Before code, [YOU] explains the input, data flow, expected output and one failure case.
- A step passes only when its gate checks ran and passed. Record counts and anything skipped.
- Use one or more focused commits per step, only when alayala asks. Do not squash.
- A fetch stub is O evidence. It never replaces an R check.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Keep mock values, synthetic test data and real published data apart in every record. A frontend screen is not a data finding. If real data shows a possible anomaly, follow the AGENTS.md anomaly workflow.
- [x] [ME] Approved the proposal direction (Q1, A26), D01–D04, and Q2–Q4. [YOU] Drafted the proposal, specification, design and these tasks, copied the handoff package and recorded A25/A26 updates.
- [x] [ME] Approve or change the [package versions](design.md#proposed-package-versions), including TypeScript 6.0.3 and Node 24.21.0. Approved October 5, 2026, with the implementation request.

### Step 2 — Scaffold and foundations (F1)

Scope: R01–R06, R15, R17, R19, R21, R59. Requires the approved package list.

- [x] [YOU] Create `frontend/` with Vite + React + TypeScript (strict). Pin the approved versions, add `.nvmrc` and `engines`, and commit `package-lock.json`. Run `npm ci` and `npm audit`; record the results and any peer warnings. Done with the official Node.js 24.21.0 build (SHA-256 checked): 240 packages, `npm audit` found 0 vulnerabilities, no peer warnings. npm 11.19 reported that `fsevents@2.3.3` has an install script not covered by `allowScripts`; it was not approved or run.
- [x] [YOU] Add the `/api` proxy to `127.0.0.1:8000`, ESLint config (including the `parseFloat`/`Number(` ban outside tests), and scripts: `dev`, `build`, `typecheck`, `lint`, `test`, `e2e`. The ban also covers `Number.parseFloat` and unary `+`; only `src/lib/**/*.test.ts` is exempt. `TRINITY_API_TARGET` can point the proxy at a disposable test API; the default stays `127.0.0.1:8000`.
- [x] [YOU] Add `tokens.css` with every handoff token, `base.css` (focus outline, reduced motion), Google Fonts link and the four logo images from the handoff copy. The images match the PROVENANCE SHA-256 values.
- [x] [YOU] Add `lib/decimal.ts`, `lib/dates.ts`, `lib/ids.ts` with unit tests: S06, S09, half-up rounding, negative values, zero capacity, invalid strings.
- [x] [YOU] Add `api/types.ts` from `docs/openapi.json`, plus a test that compares its enums with the OpenAPI file.
- [x] [YOU] Add `api/client.ts` with problem parsing, ETag capture, `Retry-After` and idempotency keys, with unit tests for each error class in the API contract table.
- [x] [YOU] Add the base components (Button, StatusBadge, Segmented, Tabs, Dialog with a focus trap, Toast, MissingChip, ShortId, Callout, Field, Switch), with component tests for keyboard use and focus.
- [ ] [ME] Review the token file against the handoff token table. The first visual check is in step 3.

Gate: `typecheck`, `lint`, `test` and `build` pass. The build output has no fixture or secret (S26 search).

Result (October 5): passed. `npm ci`, `npm audit` (0 vulnerabilities), `typecheck`, `lint`, `test` (51 tests in 7 files, O evidence) and `build` with `scripts/check-build.mjs` all passed on Node.js 24.21.0. A lint test proves that `Number(`, `parseFloat`, `Number.parseFloat` and unary `+` fail lint in application code. The [ME] token review is pending.

### Step 3 — Sign-in, session and shell (F2)

Scope: R07–R14, R60–R63.

- [x] [YOU] Add `session.ts` (D01 `sessionStorage`, expiry timer, single clear function) and `SessionProvider` with the start-up `/me` check.
- [x] [YOU] Add the sign-in page with the D04 error copy and the R08 messages. Clear the password after each attempt.
- [x] [YOU] Add the capability map, `RequireCapability`, the landing redirect and the waiting page (A2, including the Admin-only "Go to Refresh").
- [x] [YOU] Add AppShell: sidebar, context bar (R14), drawer under 960px, account block and sign-out.
- [x] [YOU] Component tests: S02, S03 (no page request), S04 with a fake clock, the shell at both widths.
- [ ] [YOU] Playwright against Docker Compose with seeded personas: S01 (no publication), S03, S04 (revoked session), S05, S22.
- [ ] [ME] Sign in as each persona in the browser and check the landing screen and sidebar.

Gate: unit, component and R checks pass. The token appears only in `sessionStorage` and the `Authorization` header.

### Step 4 — Catalog and table views (F3)

Scope: R32–R38. Facility filter: exact-ID text input until step 9.

- [x] [YOU] Catalog page from `GET /catalog`.
- [x] [YOU] Table view: filters per dataset, infinite preview pages, "Load more", calculated share column, Source %, footer per D02, restart on `409 publication_changed`.
- [ ] [YOU] Component tests: S12, S13, S14 (exact IDs, generator disabled without facility), empty result, `429`.
- [x] [YOU] Playwright R check without publication: `409 data_unavailable` shows A2.
- [ ] [ME] Compare with handoff screenshots 06–09.

Gate: O checks pass. The R data check (S12 against real rows) waits for step 7's publication decision; record it as pending.

### Step 5 — SQL Explorer (F4)

Scope: R39–R44.

- [x] [YOU] Editor with line numbers, ⌘/Ctrl+Enter, 16 KiB byte limit, example queries checked against SQL D01.
- [x] [YOU] Result states, NULL chip, `truncated` note, schema panel from catalog, `429` countdown.
- [ ] [YOU] Component tests: S15 states and S16 countdown with a fake clock.
- [x] [YOU] Playwright R check: Viewer has no SQL route and a direct `POST /queries` returns `403`; Analyst without publication gets A2.
- [ ] [ME] Compare with handoff screenshots 10–11.

Gate: O checks pass. R result checks wait for a local publication.

### Step 6 — Refresh and candidate review (F5)

Scope: R45–R54.

- [x] [YOU] Run list with cursor pages, current run, warning and blocker strip, "Start refresh" from `actions`.
- [x] [YOU] Run detail with polling, steps grouped by stage, attempt pages, failed callout.
- [x] [YOU] Candidate panel, Approve and Discard dialogs with `If-Match` and idempotency keys, `412` reload.
- [ ] [YOU] Component tests: S17 (one key across a network retry; polling stops), S18 and S19 with stubs, S20 (only enabled actions shown).
- [x] [YOU] Playwright R check: Admin starts a refresh and sees the run page poll. Record the actual final state; the worker may fail locally without EIA access.
- [ ] [ME] Compare with handoff screenshots 12–15.

Gate: O checks pass, and the R start/poll check ran with its result recorded.

### Step 7 — National dashboard: backend, then UI (F6, F7)

Scope: backend dashboard and metric endpoints; R23–R31.

- [x] [YOU] Use the existing disposable synthetic publication helpers for automated R checks. This bounded implementation assumption does not change the retained publication or claim a human data review.
- [x] [YOU] Record the national backend design in the [continuation note](design.md#continuation-design--steps-79), within the request to finish steps 3–9. No new API contract choice was introduced.
- [x] [YOU] Implement both endpoints with offline and disposable PostgreSQL tests.
- [x] [YOU] Dashboard UI: header, KPIs with count-up, meter, chart (gaps, out-of-range, hover, pin, keyboard, range morph), Daily values, selected observation, facility contributions for `preview:detail` only, sparkline.
- [ ] [YOU] Component tests: S07, S08, S10, S11; chart keyboard; reduced motion (S24).
- [ ] [YOU] Playwright R checks with the local publication: S07, S10, S11, and S12 from step 4.
- [ ] [ME] Compare with handoff screenshots 02–05.

Gate: backend tests, O and R checks pass.

### Step 8 — Settings and initial setup: backend, then UI (F8)

Scope: `PUT /settings`, `GET /settings/schedule-status`; R55–R58.

- [x] [YOU] Record the bounded backend design and implement settings with tests for compare-and-swap, one-time setup and blocker order. See the continuation note and measured results below.
- [ ] [YOU] Schedule and setup pages; S21 component and R checks. Positive component coverage now verifies navigation, initial values, all saved fields, saved UI state, setup-to-Refresh and non-admin guards; existing 412 coverage remains. Extended real-browser schedule editing is pending.
- [ ] [ME] Compare with handoff screenshot 16.

Gate: backend tests, O and R checks pass.

### Step 9 — Facility choices and run recovery: backend, then UI (F9)

Scope: facility and generator choice endpoints, rerun, delete warning; R35, R53.

- [x] [YOU] Record the bounded backend design and implement choice/recovery endpoints with offline, PostgreSQL and isolated-runtime tests.
- [x] [YOU] Replace the exact-ID input with the searchable facility list. Add the "Run again" and "Resolve warning" actions.
- [ ] [YOU] Component and R checks for S14 and S20. S14 browser assertions already cover exact `001a` and Generator gating. S20 now has positive component tests for both recovery commands, ETag/idempotency headers and refreshed UI; real-browser recovery remains pending. See [focused evidence](../../ai/sessions/2026-10-05-recovery-schedule-component-coverage.md).

Gate: backend tests, O and R checks pass.

### Steps 3–9 — measured continuation result

Implementation is complete locally. Full acceptance is **not** closed. The
[continuation evidence](../../ai/sessions/2026-10-05-frontend-steps-3-9-continuation.md)
records exact commands, corrections, authorship and remaining scenarios.

- Frontend: typecheck, lint, 69 tests and production build/bundle scan passed on Node 24.21.0.
- Backend: 382 offline passes (185 service checks skipped); 7 new PostgreSQL checks, 2 Docker query checks and 18 focused publication regressions passed.
- Browser: 5 no-publication/session/setup checks and 3 synthetic-publication/data checks passed through real HTTP. The database was native disposable PostgreSQL, not the retained Docker Compose stack.
- The refresh start/poll test ended in `requested`; no EIA worker ran. Runtime data came from synthetic Parquet and synthetic object storage through real isolated query execution.
- All [ME] visual checks remain open. Partial combined O/R task rows remain open; implementation of those pages is complete. Step 10 is not claimed.

The SQL countdown has both fake-clock component coverage and real browser rate
admission coverage. Dashboard range bounds, missing dates, keyboard selection,
Viewer detail exclusion and reduced motion have browser coverage. Table weighted
pagination, publication restart and candidate/settings stale ETags have component
coverage. Actual candidate publication/discard/recovery through the browser,
changing-publication multi-page tables, every SQL result variant and all-page
visual/accessibility acceptance still need their complete scenarios.

### Step 10 — Acceptance (F10)

Scope: all R and S items.

- [ ] [YOU] Run every unit, component and Playwright suite. Run axe on each page (S23) and a keyboard-only pass.
- [ ] [YOU] Capture screenshots at 1440px and 924px for each handoff screen.
- [ ] [ME] Compare the screenshots with the handoff (S25). List each difference as accepted or to fix.
- [ ] [YOU] Write the acceptance evidence note. Update README, NOTES (human and AI contributions, kept separate under A25) and this file with actual results.

Gate: all checks pass or have a recorded, accepted reason. Claude's code is recorded as AI work, separate from alayala's design.
