# Specification: Trinity web frontend

Date: 2026-10-04
Status: Draft specification. Alayala approved the [proposal](proposal.md) direction and selected React + TypeScript + Vite (Q1, recorded as [A26](../../DECISIONS.md#a26--frontend-stack)) when he requested this specification. On October 5 he accepted D01 (`sessionStorage`, after correcting an earlier memory-only answer), D02–D04, answered proposal Q2–Q4 and requested design and tasks. The [dependency list](#dependencies-pending-approval) still needs his approval before install. This document does not authorize implementation, dependency installation or backend changes.
Branch: `frontend`; inspected HEAD `444795f` (Figma/brand handoff commit on top of `main` `eed2ab6`).
Basis: [proposal](proposal.md); A16, A19, A20, A25 and the Viewer/SQL refinements in [DECISIONS.md](../../DECISIONS.md); [API contract](../../docs/api-contract.md); [data contract](../../docs/schema.md); [security contract](../../docs/security-contract.md).
Design input: [the handoff package copy](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md) (README, `Trinity.dc.html`, 18 screenshots, 4 logo images; `support.js` excluded). Its author is pending confirmation under A25.

## Human

### Result

A user signs in with a seeded local account and sees only the screens their role allows. Viewer sees the national dashboard. Analyst also sees Catalog, table views and SQL Explorer. Admin also sees Refresh, candidate review and Schedule settings. Every value comes from the `/api/v1` endpoints for one publication. The look, copy, states and motion follow the handoff package.

Input: the user's account and password, then clicks, filters, dates and SQL text. Flow: sign in → read `/me` → open the landing screen → call the page's endpoint with the bearer token → show the response, or a safe message for each problem code. Output: screens that match the handoff at 1440px and 924px and show exactly the published values.

Example: Analyst signs in, opens Catalog, selects `facility_outages`, sets 20–27 Sep and a facility. The table shows the published rows in key order. The footer shows the combined offline share only when every matching row is loaded.

Failure example: Viewer types `/sql` in the address bar. The app redirects to the dashboard and makes no `POST /queries` call. If a request is sent another way, the server still returns `403`.

### Choices that need your confirmation

| ID | Question | Recommendation |
|---|---|---|
| D01 — Token storage (proposal Q3) — **accepted October 5, 2026** | Where does the browser keep the session token? | **`sessionStorage`.** The token survives a reload and is removed when the tab closes. Send it only in `Authorization: Bearer`, never in a URL parameter. Clear it on sign-out, on `401` and on expiry. Never write it to `localStorage`, cookies or logs. (Alayala first answered "memory only", then corrected it to `sessionStorage`.) |
| D02 — Table rows and footer — **accepted October 5, 2026** | The mock shows "Not reported" rows and a combined share for all rows. Preview returns only existing rows, up to 1,000 per page. | Show only rows that exist. Add the per-row calculated "Offline share" and keep the source `percentOutage` as "Source %". Show the combined share only when there is no `next_cursor`; otherwise offer "Load all rows". |
| D03 — Facility contributions — **accepted October 5, 2026** | The mock lists facilities with "Not reported" on the selected date. One date of preview data cannot show which facilities are absent. | List the facilities that reported on that date. The 8-day sparkline shows absent days as gaps. Show the facility sum next to the national outage, with no claim that they must match. Analyst and Admin only. |
| D04 — Copy changes forced by contracts — **accepted October 5, 2026** | Some mock text conflicts with the contracts. | Login error says "Account or password is incorrect." (the API gives the same error for both). SQL nulls show "NULL", without "not reported". Shares show 2 decimal places (catalog `display_decimal_places`). The run list drops "Latest day" (not in `RefreshSummary`) and shows the finish time. |

## LLM

### Requirements

IDs are local to this slice. The contracts govern every data, role and error rule. The handoff governs layout, copy, tokens and motion where it does not conflict.

#### Application and build

| ID | Required behavior |
|---|---|
| R01 | Put the app in `frontend/`. Use React, TypeScript in strict mode and Vite. Pin exact versions and commit the lockfile under A17. List every runtime and development dependency for approval before install. |
| R02 | In development, the Vite server proxies `/api` to `http://127.0.0.1:8000`. The app calls relative `/api/v1/...` paths only. Add no CORS setting to the backend for local work. |
| R03 | Define every handoff color, radius, shadow, spacing and type value as a CSS custom property in one token file. Components use tokens only, not raw hex values. |
| R04 | Load Geist and Geist Mono. Use `font-variant-numeric: tabular-nums` for all metrics, tables and dates. Copy the four logo images into `frontend/` assets. |
| R05 | Ship no fixture data, regex SQL parser, role switch, data-state switch, outcome selector, "Continue as …" button or "Illustrative data" tag. A development-only mock mode is not part of this slice. |
| R05a | Install only React, TypeScript, Vite and the packages approved in [Dependencies pending approval](#dependencies-pending-approval). Any package not in that list needs separate approval. |
| R06 | Provide `npm` scripts for dev, build, type check, lint, unit tests and end-to-end tests. Build output contains no token, password or environment secret. |

#### Session and navigation

| ID | Required behavior |
|---|---|
| R07 | Sign-in posts exactly `{username, password}` to `POST /auth/login`. On `200`, keep `access_token` and `expires_at` in `sessionStorage` (D01), then fetch `GET /me`. After a reload, a stored, unexpired token is checked with `GET /me` before any page opens. Never log or display the password or token. Clear the password field after each attempt. |
| R08 | `401 invalid_credentials` shows one generic message (D04). `429` shows "Too many attempts. Try again in N seconds." from `Retry-After`. `503 auth_unavailable` shows "Sign-in is unavailable. Try again later." |
| R09 | Navigation and route guards use `/me.capabilities`, not role names. Dashboard: `national:read`. Catalog and table views: `preview:detail`. SQL: `sql:execute`. Refresh: `refresh:read`. Settings: `settings:read`. A route without its capability redirects to the landing screen and sends no request for that page. |
| R10 | After sign-in, open the route for `landing_screen`: `waiting` → unavailable screen; `setup` → setup form; `refresh_runs` → Refresh; `national_dashboard` and `explorer` → Dashboard. |
| R11 | Any `401` (`invalid_session` or `authentication_required`) clears the token and query cache, then opens sign-in with "Your session ended. Sign in again." Do not retry the request. When `expires_at` passes, clear the token and cache the same way without waiting for a `401`. The server still enforces expiry. |
| R12 | Sign out posts `{}` to `POST /auth/logout`, then clears the token and cache whether the call succeeds or returns `401`. |
| R13 | The shell matches handoff "Application shell": 224px sidebar, sticky context bar and drawer under 960px (Escape and backdrop close it; focus moves into it and returns to "☰ Menu"). The account block shows `user_id` and role. |
| R14 | The context bar shows the active `Publication`: short version ID (mono), `published_at` as `D MMM YYYY, HH:mm UTC`, `latest_observation_date`, and ● Ready. With `publication: null` it shows "No publication yet · ○ Unavailable". For Admin, a run in `awaiting_approval` adds a pill linking to that run. |

#### Values and display rules (all screens)

| ID | Required behavior |
|---|---|
| R15 | Keep decimal values as the strings the API returns. Never convert them through JavaScript `number` for arithmetic. Formatting may add thousands separators and trim to the shown decimal places without changing the value. |
| R16 | Show `null` as the missing chip ("○ Not reported") in dashboard and table views. Show `0` as `0`. Never fill a missing day with zero. |
| R17 | Calculated shares use `100 × outage ÷ capacity` with exact decimal arithmetic, rounded half-up to 2 places. Zero capacity gives "Unavailable". Combined shares use Σoutage ÷ Σcapacity, never an average of percentages. |
| R18 | Show values outside 0–100 unchanged, with the out-of-range marker and warning. Never clamp them. |
| R19 | Treat `period` and other `YYYY-MM-DD` dates as calendar dates. Never pass them through a local-time `Date` conversion. Show event times (`published_at`, `requested_at`) in UTC with the "UTC" suffix. |
| R20 | Keep three dates separate on every screen: selected observation, latest observation and publication time. |
| R21 | Show IDs (UUIDs) as the first 8 characters in mono. The full value is in a tooltip and copyable. Show `run_seq` as "Run #N". |
| R22 | Show `warning`-severity diagnostics from any analytical response as a warning callout, using the server `message`. Do not invent diagnostic text. |

#### National dashboard

| ID | Required behavior |
|---|---|
| R23 | Call `GET /dashboard/national` with `preset=30d`, `90d` or `1y`, or with both `start` and `end` for a custom range. Labels: "30 days", "90 days", "Last 365 days", "Custom range". Disable a custom range that is reversed or longer than 366 days before sending it. |
| R24 | The header and "Latest observation" block use `summary`, which is the range end date. Label the block with `summary.period`. KPIs: offline share from `summary.offline_share_percent`, outage from `summary.outage`, capacity from `summary.capacity`. If the share is null, show the reason instead of a number. |
| R25 | The meter fills to the summary share and is empty and labeled "Unavailable" when the share is null. A share above 100 fills the track and shows the out-of-range marker. |
| R26 | The chart has one x position per entry in `days`. Null days break the line and draw a hatched gap band. An isolated reported day is a 6px dot. Gridline steps, hover, click-to-pin, keyboard (←/→, Enter, Esc) and the legend follow handoff B.3. |
| R27 | The "Daily values" tab lists the same `days` entries as the chart, with Day, Outage MW, Capacity MW and Offline share. Missing days show the chip. Clicking a row pins it. Chart, table and selected-observation panel always show the same values for the same date. |
| R28 | The selected-observation panel shows the pinned date or `summary.period`, its values, and a comparison with the previous calendar day, or "Previous day (date) was not reported." |
| R29 | Facility contributions (D03) are shown only with `preview:detail`. Load `GET /datasets/facility_outages/preview?start=D&end=D&limit=1000` for the selected date and follow `next_cursor` until it is null. Rank by outage. Name = `facilityName` or the `facility` ID when the name is null. |
| R30 | The detail panel shows the selected facility's outage, calculated share and capacity. The sparkline loads that facility for the 8 dates ending on the selected date and shows absent dates as gaps. The links open the table views filtered to that facility ID. |
| R31 | A new publication (a different `publication_event_id` in any response) refreshes the dashboard and replays the first-draw and KPI count-up motion. |

#### Catalog and table views

| ID | Required behavior |
|---|---|
| R32 | Catalog lists `GET /catalog` datasets in response order. It shows each dataset's key (mono), `label` and the latest observation from `freshness`. The handoff "Rows" column is not shown, because the catalog has no row count. |
| R33 | The table view title uses the dataset key and `label`. It shows "Rows from {short version ID}." The breadcrumb returns to Catalog. |
| R34 | Filters: From, To and Facility (detailed datasets), and Generator (generator dataset, enabled only after a facility is chosen). Send only `start`, `end`, `facility`, `generator`, `limit`. Keep filters per dataset in memory for the session. "Reset filters" restores the server defaults (omit the parameters). |
| R35 | The Facility filter uses `GET /datasets/{key}/facilities` with `search`. It shows the name and sends the exact ID. Until that endpoint exists, use an exact-ID text field with the hint "Facility ID". Never trim or change the ID. |
| R36 | Render columns in response `columns` order with readable headers (`period` → Day, `facility` → Facility ID, `facilityName` → Facility, `generator` → Unit, `capacity` → Capacity MW, `outage` → Outage MW, `percentOutage` → Source %). Add the calculated "Offline share" column (R17). The table has a 720px minimum width and scrolls horizontally. |
| R37 | "Load more" follows `next_cursor` with the same filters. `409 publication_changed` clears the pages and shows "The data was updated. The table restarted from the first page." An empty result shows "No rows match these filters." |
| R38 | Footer per D02: the combined share and row count when every row is loaded; otherwise "Showing N rows. Load all rows to calculate the combined share." The legend line about "○ Not reported" versus `0` stays. |

#### SQL Explorer

| ID | Required behavior |
|---|---|
| R39 | The editor matches handoff D (mono text, line numbers, growing height). ⌘/Ctrl+Enter and "Run query" post `{sql}` to `POST /queries`. Disable Run for blank text or text over 16 KiB (UTF-8 bytes), with the reason shown. |
| R40 | Default query: `SELECT period, facility, "facilityName", capacity, outage FROM facility_outages ORDER BY period, facility LIMIT 100`. The example buttons run real queries that the backend accepts or rejects; none uses a fixture. Double quotes keep the exact spelling of `facilityName` and `percentOutage` ([SQL D01](../single-table-sql/spec.md#d01--accepted-first-sql-grammar)). |
| R41 | States: idle, loading (skeleton and "Running…"), results ("N rows · M ms" from `returned_rows` and `execution_ms`), empty ("The query ran and returned 0 rows."), and error (problem `detail` in the red callout). If `truncated` is true, say "Showing the first 1,000 rows. Add LIMIT or filters to see the rest." |
| R42 | Result cells show values as returned. Null shows a "NULL" chip (D04). Column headers show the name and, if not null, the unit. |
| R43 | The schema panel lists datasets and columns from `GET /catalog` (name, type, nullable). Remove the prototype's "fixtures" note. |
| R44 | `429 rate_limited` disables Run for the `Retry-After` seconds, with a countdown. `504 query_timeout` and `503 query_resource_limit` show the safe message and keep the SQL text. |

#### Refresh and candidate review (Admin)

| ID | Required behavior |
|---|---|
| R45 | Refresh lists `GET /refresh-runs` items (Run #, requested time, status, finished time). "Load older" follows `next_cursor`. Show `active_run`, `unresolved_warning` and `blocker` from every response above the table. |
| R46 | "Start refresh" is enabled only when the `refresh:start` action in `actions` has `enabled: true`. Otherwise show its `reason_code` as text below the button. |
| R47 | Every command (start, rerun, delete warning, approve, publication retry, discard) creates one UUID `Idempotency-Key` for each user confirmation. The client reuses that key when it automatically retries the same request after a network failure, and never for a new click. Commands send `{}` (DELETE sends no body). |
| R48 | Status labels: `requested`/`running` → ◐ Running; `awaiting_approval` → ! Awaiting review; `publishing` → ◐ Publishing; `publication_failed` → ✕ Publication failed; `failed` → ✕ Failed; `succeeded` → ✓ Published; `discarded` → – Discarded; `superseded` → – Superseded. Each label has its glyph, text and color. |
| R49 | Run detail reads `GET /refresh-runs/{run_id}` and polls it every `poll_after_seconds` while that field is not null. Polling stops when it is null and when the page closes. Closing the page does not cancel the run. |
| R50 | The steps list groups `steps` by `stage` in the order extract → prepare → validate → publish (labels Retrieve, Prepare, Validate, Publish), after an "Accepted" row from `requested_at`. Each attempt shows status, progress (`processed_count` / `total_count` or "unknown total"), duration and `error_summary`. "Show more attempts" follows `next_steps_cursor`. |
| R51 | When `candidate` is not null, the review panel reads `GET /candidates/{version_id}` and keeps its `ETag`. It shows checks passed (`passed_required_count` / `expected_required_count`), warning diagnostics with server messages, review status and publication progress. It states that the current publication stays in place until approval. |
| R52 | Approve and Discard are shown only when the matching action is enabled. Each opens the handoff confirmation dialog. Confirming sends the command with `If-Match` set to the candidate `ETag`. `412` reloads the candidate and shows "This candidate changed. Review it again." |
| R53 | Failed and publication-failed runs show the red callout with the current publication. "Run again", "Resolve warning" and "Retry publication" are shown when their actions are enabled, use the run or candidate ETag, and use the same dialog pattern. |
| R54 | After any accepted command, refresh the run, run list, `/me` and the context bar. After a run reaches `succeeded`, also refresh catalog, dashboard and table queries. |

#### Settings and initial setup (Admin)

| ID | Required behavior |
|---|---|
| R55 | Schedule reads `GET /settings` and keeps its `ETag`. Fields: "Schedule enabled" (`role="switch"`), Time (`HH:mm`) and Timezone (IANA names from `Intl.supportedValuesOf('timeZone')`). |
| R56 | Save is disabled until a value changes. Save sends `PUT /settings` with all three fields and `If-Match`. `412` reloads the settings and shows "Settings changed in another session. Review and save again." Status text follows handoff F. |
| R57 | Show `GET /settings/schedule-status`: the next check in local form, or the blocker message. Keep the note "This only sets the clock. It does not start a refresh." |
| R58 | When `setup_completed_at` is null (landing `setup`), show the same form titled "Set up Trinity" with a "Complete setup" button. After success, go to Refresh. |

#### Errors, accessibility and motion

| ID | Required behavior |
|---|---|
| R59 | One API client parses `application/problem+json`. It maps `code` to the messages in this spec. Unknown codes show "Something went wrong. Request ID: {request_id}." Never show stack traces or raw response bodies. |
| R60 | `409 data_unavailable` on any analytical page shows handoff A2 ("Nothing to show yet"). Admin also sees "Go to Refresh". Viewer and Analyst never see admin actions. |
| R61 | Every interactive element works with the keyboard and has the global focus outline. Dialogs trap focus and return it on close. Status changes (query done, run status, saved) are announced through an `aria-live` region. Text contrast meets WCAG 2.2 AA. |
| R62 | Motion follows handoff "Interactions and motion". Under `prefers-reduced-motion: reduce`, all transitions, the chart morph and the count-up are disabled, and final values appear at once. |
| R63 | At 960px and above, the sidebar is pinned. Below 960px it is a drawer. Pages have no horizontal page scroll down to 360px wide; wide tables scroll inside their own container. |

### Mockup-to-contract mapping

| Mock element | Contract source | Rule |
|---|---|---|
| `pub-2026-09-28-a` | `Publication.version_id`, `publication_event_id` | R21 short ID |
| `ver-19c` | `CandidateRef.version_id` | R21 |
| `run-1044` | `Run.run_seq`, `run_id` | "Run #N" |
| Plant name filter | `facility` (ID) + `facilityName` (label) | R35 |
| `facility_name` in SQL | `facilityName` column | R40, R43 |
| Fleet offline 14.4% | `summary.offline_share_percent` (2 dp) | R24, D04 |
| Accepted → Retrieve → Prepare → Validate → Review | `requested_at`, `Step.stage`, `CandidateRef.review_status` | R50 |
| Run list "Latest day" | not in `RefreshSummary` | D04 |
| Catalog "Rows" | not in `Dataset` | R32 |
| SQL truncation at 200 | `truncated`, 1,000-row cap | R41 |

### Acceptance scenarios

None has run. O = unit/component test; R = Playwright against the local Docker API with seeded personas; H = human visual check against the handoff screenshots.

| ID | Scenario and expected observation | Requirements | Evidence |
|---|---|---|---|
| S01 | Each persona signs in and lands on the screen for its `landing_screen`, with and without a publication. | R07, R10 | R |
| S02 | Wrong password and unknown account show the same message. The password field is empty after the attempt. | R07–R08 | O/R |
| S03 | Viewer opens `/catalog`, `/tables/facility_outages`, `/sql`, `/refresh`, `/settings` by URL. Each redirects, and no request for that page is sent. Analyst opens `/refresh` and `/settings`, with the same result. | R09 | R |
| S04 | The session is revoked on the server while a page is open. The next request opens sign-in with the session-ended message. A fake clock past `expires_at` clears the session without a request. A reload keeps the session; a new tab does not. `localStorage`, cookies and URLs never contain the token. | R07, R11 | O/R |
| S05 | Sign out, then reuse the old token with a direct API call. The API returns `401`. | R12 | R |
| S06 | Formatting `"100056.000000"`, `"-12.5"` and `"0"` keeps the exact value. The share for `outage "14420"`, `capacity "100056"` is `14.41`. Zero capacity is "Unavailable". | R15, R17 | O |
| S07 | A dashboard with null days shows gaps in the chart, the chip in Daily values and the same values in the selected-observation panel. | R16, R26–R28 | O/R/H |
| S08 | A value of 102.40 is shown unchanged, with the out-of-range marker and warning. | R18, R22, R25 | O/H |
| S09 | `period "2026-09-27"` is shown as 27 Sep 2026 in the `America/Los_Angeles` and `Asia/Tokyo` time zones. | R19 | O |
| S10 | A custom range of 367 days or a reversed range cannot be sent. 30d, 90d and 1y send the matching preset. | R23 | O/R |
| S11 | Viewer's dashboard has no facility contributions and makes no facility preview request. | R29 | R |
| S12 | The table view loads two pages with "Load more". The combined share appears only after the last page. | R37–R38 | O/R |
| S13 | The publication changes between table pages. The table restarts with the message. | R37 | O/R |
| S14 | Facility IDs with leading zeros are sent exactly. Generator is disabled until a facility is selected. | R34–R35 | O/R |
| S15 | SQL: a valid query, an empty result, a disallowed query and a query that returns more than 1,000 rows each show the right state. Null shows "NULL". | R39–R42 | O/R |
| S16 | SQL: 31 runs in 60 seconds give `429`. Run stays disabled for the countdown. | R44 | R |
| S17 | Admin starts a refresh. A network failure and retry reuse one `Idempotency-Key`. The run page polls and stops at a final state. | R46–R49 | O/R |
| S18 | A candidate with warnings: approve with a stale ETag gives `412` and a reload. Approve with the current ETag publishes, and the context bar shows the new publication. | R51–R52, R54 | R |
| S19 | Discard a candidate. The run shows Discarded, and the publication does not change. | R52, R54 | R |
| S20 | A failed run shows the callout and only its enabled recovery actions. | R53 | R |
| S21 | Settings: Save is disabled until a change. A stale ETag gives `412` and a reload. Setup completion moves to Refresh. | R55–R58 | O/R |
| S22 | Without a publication, every analytical page shows "Nothing to show yet". Only Admin sees "Go to Refresh". | R60 | R |
| S23 | All flows work with the keyboard only. The dialogs trap focus. An automated accessibility check reports no serious violations. | R61 | O/R |
| S24 | With reduced motion, no transition or animation runs. | R62 | O/H |
| S25 | Each handoff screenshot is matched at 924px, and the shell at 1440px. Differences are listed and accepted or fixed. | R03–R04, R13, R63 | H |
| S26 | The production build has no fixture data, prototype controls, token or password. | R05–R06 | O |

### Dependencies pending approval

A26 approves React, TypeScript and Vite only. Every other package below is a proposal. Exact versions follow A17 and are fixed in design. "No dependency" is a real option for each row.

| Package | Kind | Purpose | Without it |
|---|---|---|---|
| `react`, `react-dom` | runtime | React itself; `react-dom` renders it in the browser. Treated as part of the React approval. | — |
| `@vitejs/plugin-react` | development | Vite's official React plugin (JSX, fast refresh). | Hand-written Vite config for JSX; no fast refresh. |
| `react-router` | runtime | Pages, URL routes and capability guards (R09). | A small hand-written router; more code to test. |
| `@tanstack/react-query` | runtime | API cache, polling (R49), invalidation after publication (R54). | Hand-written fetch hooks, polling and cache. |
| `@types/react`, `@types/react-dom` | development | TypeScript types for React. | Weaker type checks. |
| `eslint`, `@eslint/js`, `globals`, `typescript-eslint`, `eslint-plugin-react-hooks` | development | Lint, including the React hook rules. | Type check only. |
| `vitest`, `jsdom` | development | Unit and component tests (O evidence). | No automated frontend unit tests. |
| `@testing-library/react`, `@testing-library/dom` (required peer), `@testing-library/user-event`, `@testing-library/jest-dom` | development | Component tests that act like a user. | Lower-level tests with less coverage of behavior. |
| `@playwright/test` | development | End-to-end role and flow tests against the Docker API (R evidence). | Manual browser checks only. |
| `@axe-core/playwright` | development | Automated accessibility check (S23). | Manual accessibility review only. |

Not proposed: a chart library, a CSS framework, a decimal library (scaled `BigInt` is enough for R15/R17), a motion library (CSS and the Web Animations API), a font package (Geist is loaded from Google Fonts, as in the handoff).

### Remaining design obligations

- Exact versions of the approved packages under A17, including the Node version.
- Folder structure, route map and the API client and query-key design.
- The scaled `BigInt` decimal method and its tests.
- How Playwright gets a publication: synthetic local state or a recorded live run. Mock values are never EIA evidence.
- Which backend slices (dashboard, metric, settings write, schedule status, filter choices, rerun and resolve-warning commands) run in this branch, and in what order.

## Review gate

Alayala approves or changes the dependency list and the versions in [design](design.md#proposed-package-versions). [YOU] drafted [design](design.md) and [tasks](tasks.md) on October 5. Implementation starts only when he asks.
