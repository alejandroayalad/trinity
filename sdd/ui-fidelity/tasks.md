# Tasks: UI fidelity to the handoff screenshots

Date: 2026-10-06
Status: V0–V9 implemented by [YOU] on 2026-10-06; V10 checks run. See [Progress](#progress--2026-10-06). Open: alayala's look at the V9 state captures, commits.
Branch: `ui/handoff-fidelity` (from `origin/main` `bf52757`).
Basis: [proposal](proposal.md), [specification](spec.md), [design](design.md) and the frontend change in [sdd/frontend](../frontend/tasks.md). Its R and S items stay valid; this change refines visuals and copy only.
Design attribution: alayala created the mockups in Figma; the brand reference was made with ChatGPT. See [NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026) and A25. AI work in this change is implementation only.

## Human

The work has one ongoing evidence step and eleven slices, V0–V10. Do them in order. Each slice changes one area and ends with the same exit check.

Rules for every slice:

- Matching a handoff screenshot needs no per-screen approval. alayala waived it on 2026-10-06.
- States with no Figma design use only prototype patterns. [YOU] shows their screenshots to alayala (V9).
- Before code, [YOU] explains the input, data flow, expected output and one failure case.
- No backend, API, contract, permission, dependency or lockfile change. Data flow, TanStack Query use, retries and permissions stay the same.
- Contracts win over the mock (A9, A16, A19, A20, A25). Mock values such as `run-1044` are design examples, not EIA data.
- Update a test only where the spec changes copy or layout. Do not weaken an assertion to make it pass.
- No commit unless alayala asks. Suggested boundary: one commit per slice, message `ui-fidelity Vn: <area>`. Do not squash.

Exit check prerequisites: run every command from `frontend/`. The e2e configs have no `webServer`, so `npm run dev` must already run on `127.0.0.1:5173`. All e2e API calls are synthetic `page.route` responses; no backend is needed. Run the presentation config first; it writes to `test-results/ui-fidelity-<slice>`. The fidelity config then writes to the `pages/` subfolder, so it does not lose the presentation output.

Handoff folders: `H/` = `docs/design-reference/2026-10-04-explorer-handoff/screenshots/`; `R/` = `docs/design-reference/2026-10-04/`.

## LLM

### Step 1 — Maintain data evidence — ongoing

- [ ] [YOU] Make no EIA calls in this change. Keep mock values, synthetic e2e data and real published data apart in every record. A screenshot is not a data finding.
- [ ] [YOU] If a real-data anomaly appears, follow the AGENTS.md anomaly workflow in `FINDINGS.md`. This step stays open after V10.

### Step 2 — V0 Baseline capture

Goal: capture the current app at 1440 and 924 px before any style change. Refs: UF-V*.
Files: new `frontend/tests/e2e/fidelity.config.ts`, new `frontend/tests/e2e/fidelity.spec.ts`, new `sdd/ui-fidelity/acceptance.md` (difference list, started here).

- [ ] [YOU] Create `fidelity.config.ts` from the `presentation.config.ts` pattern: `testMatch: 'fidelity.spec.ts'`, `workers: 1`, `baseURL` `http://127.0.0.1:5173`, `outputDir` `../../test-results/ui-fidelity`.
- [ ] [YOU] Create `fidelity.spec.ts`. Synthetic `/me` per role and synthetic page responses, defined in the test file only. Set reduced motion. For each screen, take a full-page screenshot at 1440×900 and 924×900, named `<NN>-<screen>-<width>.png` with the `H/` number.
- [ ] [YOU] Cover the handoff screens: sign-in, dashboard top, contributions, 90 days, daily values, viewer dashboard, catalog, table facility/generator/national, SQL, SQL error, refresh runs, run review, discard dialog, run failed, settings, viewer unavailable.
- [ ] [YOU] Run the exit check with slice `v0`. In `acceptance.md`, list the main gap per screen against `H/` and `R/`. Mark each row "to fix" or "contract difference".

Compare: all of `H/01`–`H/18` and `R/01`–`R/12`.
Exit check: `npm run typecheck` · `npm run lint` · `npm test` · `npm run e2e -- --config tests/e2e/presentation.config.ts --output test-results/ui-fidelity-v0 --reporter=line` · `npm run e2e -- --config tests/e2e/fidelity.config.ts --output test-results/ui-fidelity-v0/pages --reporter=line`

### Step 3 — V1 Base styles

Goal: remove global element rules and adopt the prototype surfaces and content width. Refs: UF-B*.
Files: `frontend/src/styles/app.css`, `frontend/src/styles/base.css` (keep helpers), `frontend/src/shell/AppShell.tsx`, new `frontend/src/shell/AppShell.module.css`, one new `*.module.css` beside each page in `frontend/src/pages/**` (names per design.md).

- [ ] [YOU] Remove the global `label`, `input`, `table` and `h2` rules from `app.css`. Fix any layout that depended on them in the page module.
- [ ] [YOU] Swap surfaces: sidebar `#F0F0F0`, main `#FFFFFF`. Content max 1248 px, left-aligned. Use `tokens.css` values only.
- [ ] [YOU] Replace the undefined `app-shell` class and the `.panel` card wrapper with CSS Module classes.
- [ ] [YOU] Check focus-visible, reduced motion and the 960 px drawer breakpoint (R63) still work at 320 px.

Compare: `H/02-dashboard-top.png`, `H/06-catalog.png`, `H/12-refresh-runs.png`.
Exit check: same commands as V0 with `v1` in both output paths.

### Step 4 — V2 Shell

Goal: sidebar, context bar, account block and drawer match the prototype. Refs: UF-S*.
Files: `frontend/src/shell/AppShell.tsx`, `frontend/src/shell/AppShell.module.css`, `frontend/src/session/capabilities.tsx`, `frontend/src/pages/pages.test.tsx`, `frontend/src/session/session.test.tsx`.

- [ ] [YOU] Brand block: 28 px mark, 84 px wordmark, "OUTAGE EXPLORER" caption. Nav items 36 px; active item white with border and weight 600.
- [ ] [YOU] Rename nav labels to "Dashboard" and "Settings". Add the "ADMINISTRATION" group label and the Refresh count pill.
- [ ] [YOU] Account block: 30 px slate initial avatar, name, role, small Sign out.
- [ ] [YOU] Context bar 52 px: Publication / Published / Latest observation, Ready and Unavailable pills, right warning pill for a run that awaits review. IDs stay short mono with tooltip (R21). No "Illustrative data" pill (R05).
- [ ] [YOU] Drawer under 960 px: slide transform and backdrop; keep keyboard and focus behavior.
- [ ] [YOU] Update tests that assert "Overview" or the "Schedule" nav link.

Compare: `H/02-dashboard-top.png`, `H/12-refresh-runs.png`, `R/08-analyst-dashboard.png`, `R/09-viewer-dashboard.png`.
Exit check: same commands as V0 with `v2` in both output paths.

### Step 5 — V3 Dashboard

Goal: the national dashboard matches the prototype layout and chart style. Refs: UF-D*.
Files: `frontend/src/pages/dashboard/Dashboard.tsx`, `NationalChart.tsx`, `Sparkline.tsx`, `chartGeometry.ts`, new `Dashboard.module.css`; `frontend/src/lib/dates.ts` (use existing `formatDay`/`formatShortDay`/`formatDayRange`); `frontend/src/pages/pages.test.tsx`, `frontend/tests/e2e/presentation.spec.ts`, `frontend/tests/e2e/data.spec.ts`.

- [ ] [YOU] Header: title, right-side Publication / Published / Observation list. KPI row with vertical dividers, not cards. KPI heading uses `summary.period` (R24).
- [ ] [YOU] Meter: full-width 10 px slate bar, legend and formula line. Missing values never show as zero.
- [ ] [YOU] Controls: `Segmented` range (spec R23 labels unless spec.md records a change), range label from `formatDayRange`, `Tabs` for Chart / Daily values.
- [ ] [YOU] Chart: 44 px gutter, 260 px plot, 2 px slate line, hatch gap bands with dashed sides, 4 short-date ticks, tooltip card, pinned orange dot, legend and hint. Keep keyboard and reduced motion.
- [ ] [YOU] Daily values: sticky header, 420 px scroll, row click pins, Latest / Pinned tag. Selected-observation panel with an always-visible "Latest observation" button.
- [ ] [YOU] Facility contributions (only with `preview:detail`, R29): ranked bar list, detail panel, links, 64 px sparkline with gap bands. Make "Selected range loaded." screen-reader only.
- [ ] [YOU] Update copy assertions ("Offline share over time", ISO date headings, `startsWith('2026-')` tick check) to the spec copy.

Compare: `H/02-dashboard-top.png`, `H/03-dashboard-contributions.png`, `H/04-dashboard-90-days.png`, `H/05-dashboard-daily-values.png`, `R/08-analyst-dashboard.png`, `R/09-viewer-dashboard.png`.
Exit check: same commands as V0 with `v3` in both output paths.

### Step 6 — V4 Catalog and table view

Goal: catalog rows and table view match the prototype. Refs: UF-C*.
Files: `frontend/src/pages/catalog/Catalog.tsx`, `TableView.tsx`, `Choices.tsx`, new `Catalog.module.css`; `frontend/src/pages/shared.tsx` (`DataTable`), `frontend/src/components/controls/Field.tsx`.

- [ ] [YOU] Catalog: 4-column grid (Table, Dataset, Latest observation, →), 52 px link rows with hover. Keep the Rows column omitted (R32). The contract has no level field (spec UF-C02).
- [ ] [YOU] Table view: breadcrumb "Catalog / name", sans title, 34 px filters with 12 px muted labels in one row, row count right.
- [ ] [YOU] Table: header without fill, 12 px header text, 14 px body, `--color-border-3` row dividers. Scope the 720 px minimum width to this table only (UF-C06); remove the global `table` rule.

Compare: `H/06-catalog.png`, `H/07-table-facility.png`, `H/08-table-generator.png`, `H/09-table-national.png`, `R/06-plant-preview.png`, `R/07-catalog.png`.
Exit check: same commands as V0 with `v4` in both output paths.

### Step 7 — V5 SQL Explorer

Goal: editor, results and schema panel match the prototype. Refs: UF-Q*.
Files: `frontend/src/pages/sql/SqlExplorer.tsx`, new `SqlExplorer.module.css`, `frontend/src/pages/shared.tsx` (`DataTable` with `sql`).

- [ ] [YOU] Aside 272 px, toggled by "Tables ▾". Schema rows 34 px with +/− and field/type columns.
- [ ] [YOU] Editor: 8 px radius, gutter with background and right border, 22 px lines, 13.5 px mono, grows with content.
- [ ] [YOU] Footer bar: Examples chips, spacer, hint, 34 px orange Run query.
- [ ] [YOU] Results: "Results" heading with "N rows · X ms", idle text, dashed empty box, red "✕ Query error" box, mono cells, sticky header, 440 px scroll.

Compare: `H/10-sql-explorer.png`, `H/11-sql-error.png`, `R/04-sql-tables.png`, `R/05-sql-results.png`.
Exit check: same commands as V0 with `v5` in both output paths.

### Step 8 — V6 Refresh list, run detail and candidate review

Goal: refresh screens match the prototype and show sentences, not codes. Refs: UF-R*.
Files: `frontend/src/pages/refresh/Refresh.tsx`, new `Refresh.module.css`, `frontend/src/components/feedback/StatusBadge.tsx`, `frontend/src/components/overlay/Dialog.tsx` (no style change expected).

- [ ] [YOU] List: subtitle, summary strip (Current publication / Awaiting review / sentence), 50 px grid rows with arrow, orange "Start refresh".
- [ ] [YOU] Run detail: "Run #N" mono label (R21) with large badge, subtitle sentence, step timeline (Accepted, Retrieve, Prepare, Validate, Publish) with 24 px status circles and right duration.
- [ ] [YOU] Candidate card: warning callout with server `message` (R22), replacement sentence, orange Approve, red-text Discard, discard note. Failed run callout.
- [ ] [YOU] Replace `reason_code` and `blocker.code` display with sentences from the V9 copy module (create the module here if V9 has not).

Compare: `H/12-refresh-runs.png`, `H/13-run-review-ver-19c.png`, `H/14-run-discard-dialog.png`, `H/15-run-failed.png`, `R/02-refresh-review.png`, `R/03-refresh-history.png`.
Exit check: same commands as V0 with `v6` in both output paths.

### Step 9 — V7 Settings and setup

Goal: schedule and setup pages match the prototype column. Refs: UF-T*.
Files: `frontend/src/pages/settings/Settings.tsx`, new `Settings.module.css`, `frontend/src/components/controls/Switch.tsx`, `Field.tsx`, `frontend/src/pages/pages.test.tsx`.

- [ ] [YOU] Title "Schedule", subtitle, bare 420 px column. Switch row with "Runs daily at HH:MM TZ." and divider. Time and Timezone fields. Clock-only note.
- [ ] [YOU] Save disabled and pale when clean; "No unsaved changes." / "Unsaved changes.". Restyle the schedule status panel with prototype patterns.
- [ ] [YOU] Apply the same column to `/setup`. Update "Save schedule" assertions to the spec copy.

Compare: `H/16-settings-schedule.png`, `R/01-settings.png`.
Exit check: same commands as V0 with `v7` in both output paths.

### Step 10 — V8 Sign-in and waiting

Goal: sign-in card and the no-publication page match the prototype. Refs: UF-A*.
Files: `frontend/src/pages/signin/SignIn.tsx`, new `SignIn.module.css`, `frontend/src/pages/unavailable/Waiting.tsx`, new `Waiting.module.css`, `frontend/src/components/controls/Button.tsx` (`full`).

- [ ] [YOU] Sign-in: 10 px radius card, 32 px padding, 36 px mark, 112 px wordmark, caption, brand line, full-width button.
- [ ] [YOU] Waiting: close the layout gap; "Go to Refresh" uses the secondary button (Admin only, A2).

Compare: `H/01-sign-in.png`, `H/17-viewer-unavailable.png`, `H/18-sign-in-after.png`, `R/10-login.png`, `R/11-no-publication.png`, `R/12-trinity-brand.png`.
Exit check: same commands as V0 with `v8` in both output paths.

### Step 11 — V9 Undesigned states and copy map

Goal: every state without a design uses the pattern map; raw codes become sentences. Refs: UF-X*.
Files: one copy module (proposed `frontend/src/lib/copy.ts` + `copy.test.ts`; use the design.md name if it differs), `frontend/src/pages/shared.tsx` (`PageError`, `Diagnostics`), `frontend/src/components/feedback/States.tsx`, `Callout.tsx`, `Toast.tsx`, `frontend/src/main.tsx` or `frontend/src/App.tsx` (mount `ToastProvider`), affected pages, `frontend/tests/e2e/fidelity.spec.ts`.

- [ ] [YOU] Copy module: map `reason_code`, blocker codes, review and publication status and stage strings to sentences. Unit-test every mapped code and the unknown-code fallback. Keep `frontend/src/api/messages.ts` for API errors.
- [ ] [YOU] Apply the pattern map: blocking → error callout; needs attention → warning callout; neutral → info callout or muted text; no rows → dashed `EmptyState`; lifecycle → badge pill; confirmation → `Dialog`; brief success → `Toast`.
- [ ] [YOU] Cover session, error, dashboard, table, SQL, refresh and settings states listed in spec.md UF-X*. No new visual vocabulary.
- [ ] [YOU] Add each state to `fidelity.spec.ts` with synthetic responses. Show the screenshots to alayala and record his reply in `acceptance.md`.

Compare: prototype patterns only (callouts, dashed box, pills in `Trinity.dc.html`); no direct screenshot.
Exit check: same commands as V0 with `v9` in both output paths.

### Step 12 — V10 Verification and record

Goal: prove the whole change and record the result. Refs: UF-V*, frontend S25.
Files: `sdd/ui-fidelity/acceptance.md`, new `ai/sessions/2026-10-06-ui-fidelity.md`, `NOTES.md` (new contribution entry), this file (results).

- [ ] [YOU] Run from `frontend/`: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` (includes `scripts/check-build.mjs`).
- [ ] [YOU] Run all synthetic e2e configs:
  `npm run e2e -- --config tests/e2e/session-reliability.config.ts --output test-results/ui-fidelity-v10-session --reporter=line`
  `npm run e2e -- --config tests/e2e/explorer.config.ts --output test-results/ui-fidelity-v10-explorer --reporter=line`
  `npm run e2e -- --config tests/e2e/presentation.config.ts --output test-results/ui-fidelity-v10 --reporter=line`
  `npm run e2e -- --config tests/e2e/fidelity.config.ts --output test-results/ui-fidelity-v10/pages --reporter=line`
- [ ] [YOU] Run `git diff --check` from the repository root. Review the full diff for files outside the slices.
- [ ] [YOU] Compare the 1440 and 924 screenshots with `H/` and `R/` (S25). In `acceptance.md`, mark each difference "fixed" or "accepted contract difference" with the rule (for example R32, R21, R05).
- [ ] [YOU] Write the session record and the NOTES.md entry. Keep alayala's Figma design, the ChatGPT brand reference and the AI implementation separate (A25). Record counts, skipped checks and the default `playwright.config.ts` suite as not run if no backend runs.
- [ ] [ME] Optional final look at the screenshots, including the V9 states.
- [ ] [ME] Commit when ready, one commit per slice as suggested above.

Gate: all listed checks pass or have a recorded reason. Step 1 stays open.

## Progress — 2026-10-06

Checkboxes above stay as the plan. This section records what ran. Evidence and the difference list: [acceptance.md](acceptance.md).

- Done [YOU]: V0 capture spec and fixtures; V1 global `app.css` removed; V2 shell; V3 dashboard and chart; V4 catalog and table view; V5 SQL Explorer; V6 refresh list, run timeline and candidate card; V7 schedule and setup; V8 sign-in and waiting; V9 copy module (`frontend/src/lib/copy.ts`), pattern-map states and three state captures.
- Done [YOU]: V10 commands — typecheck, lint, 136 unit tests, build with `check-build.mjs`, and the presentation, explorer, session-reliability and fidelity Playwright configs. Results are in acceptance.md.
- Open [ME]: look at the `X-*` state captures (UF-X12) and the page captures; say which differences to fix.
- Open [ME]: commits. Suggested slices: SDD documents; capture spec; shell and base styles; pages; tests.
- Not run: `tests/e2e/session.spec.ts` and `data.spec.ts` need the live local stack; axe checks in `session.spec.ts` therefore did not run.
- Step 1 stays open.
