# Design: Trinity web frontend

Date: 2026-10-05
Status: Approved for implementation on October 5, 2026. Alayala requested design and tasks after approving the [specification](spec.md) D01–D04. Later the same day he asked Claude to implement all ten frontend tasks from this design and these [tasks](tasks.md), with the [package versions](#proposed-package-versions) below, Node.js 24.21.0 and TypeScript 6.0.3, and to commit each slice. Backend parts follow the bounded design notes in the task steps.
Branch/inspection: `frontend`, HEAD `444795f`. No `frontend/` folder exists.
Basis: [specification](spec.md), [proposal](proposal.md), A17, A19, A20, A25 and A26 in [DECISIONS.md](../../DECISIONS.md), [API contract](../../docs/api-contract.md), [security contract](../../docs/security-contract.md), [handoff copy](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md).
Evidence: [session record](../../ai/sessions/2026-10-04-frontend-plan-and-spec.md).

## Human

### What will change

Add a `frontend/` folder with a React + TypeScript app built by Vite. During development, the browser opens the Vite server. Vite sends every `/api` request to the local API on port 8000, so the browser sees one address and the backend needs no change.

The app has four layers:

1. **Design tokens and small components.** Colors, type and spacing from the handoff, as CSS variables. Buttons, badges, dialogs and the missing-value chip use only those variables.
2. **API client.** One function sends every request. It adds the bearer token, reads problem responses and keeps `ETag` and `Retry-After` values.
3. **Session and routes.** The token lives in `sessionStorage`. `/me` capabilities decide which routes exist. A route without its capability redirects before any request.
4. **Pages.** One folder per page: sign-in, dashboard, catalog and tables, SQL, refresh, settings.

Example: Analyst opens a facility table. The page asks the API client for `/datasets/facility_outages/preview?start=…&end=…`. The client adds `Authorization: Bearer …`. Vite forwards the request to `127.0.0.1:8000`. The response rows stay decimal strings. The page adds the calculated share with exact integer arithmetic, not JavaScript floating-point numbers.

Failure: the session expires while the SQL page is open. The next call returns `401 invalid_session`. The client clears `sessionStorage` and the cache, and opens sign-in with "Your session ended." It does not resend the SQL.

### Delivery boundary

- **New packages:** only those in the approved list. A26 covers React, TypeScript and Vite. The other packages wait for alayala's approval.
- **Frontend-only steps:** sign-in, shell, catalog and tables, SQL, and refresh use endpoints that exist today.
- **Steps that need backend work:** the dashboard, settings writes, the facility list and run recovery. Each backend part follows the existing API contract and [backend structure](../../docs/backend.md), and gets its own tests.
- **Mockup values** are not data. Tests use contract-shaped synthetic responses. Real-data checks wait for a local publication.

## LLM

### Inspected baseline

| Fact | Evidence |
|---|---|
| No frontend code | `frontend/` does not exist at `444795f`. |
| Backend routes | Search for `@router.` in `backend/src/trinity/`: auth (login, logout, `/me`), `GET /settings`, `GET /catalog`, `POST /queries`, preview, refresh runs (POST, list, detail), candidates (GET, approval, publication-retry, discard). |
| Missing routes | dashboard, offline-share metric, `PUT /settings`, schedule status, facility and generator choices, rerun, delete warning. |
| Headers | `errors.py` sets `X-Request-ID` and `Cache-Control: no-store`. The settings, refresh and candidate routers handle `ETag`/`If-Match`. |
| Local API | `compose.yaml` publishes the API on `127.0.0.1:8000`. Personas are created with `python -m trinity.auth.seed`. |
| Local Node | `node -v` = v26.3.0, `npm -v` = 11.16.0. Current Node LTS is v24.21.0 (nodejs.org dist index). |

### Proposed package versions

Versions are the current npm `latest` values, read with `npm view` on October 5, 2026. Peer ranges were read the same way. Pin exact versions (no `^` or `~`) and commit `package-lock.json` (A17). Install with `npm ci`.

| Package | Version | Kind | Status |
|---|---|---|---|
| Node.js | 24.21.0 LTS (`.nvmrc`, `engines`) | runtime | proposed |
| `react`, `react-dom` | 19.3.0 | runtime | A26 |
| `typescript` | **6.0.3** | development | A26; version proposed |
| `vite` | 8.3.2 | development | A26 |
| `@vitejs/plugin-react` | 6.1.1 (peer `vite ^8`) | development | pending approval |
| `@types/react`, `@types/react-dom` | 19.3.0 | development | pending approval |
| `react-router` | 8.4.0 (peer `react >=19.2.7`) | runtime | pending approval |
| `@tanstack/react-query` | 5.104.1 (peer `react ^18 \|\| ^19`) | runtime | pending approval |
| `eslint`, `@eslint/js`, `globals` | 10.12.0, 10.0.1, 17.13.0 | development | pending approval |
| `typescript-eslint` | 8.71.0 (peer `typescript >=4.8.4 <6.1.0`) | development | pending approval |
| `eslint-plugin-react-hooks` | 7.1.1 | development | pending approval |
| `vitest`, `jsdom` | 5.0.3, 30.1.2 | development | pending approval |
| `@testing-library/react`, `@testing-library/dom`, `@testing-library/user-event`, `@testing-library/jest-dom` | 16.3.3, 10.4.2, 14.6.7, 7.0.1 | development | pending approval |
| `@playwright/test`, `@axe-core/playwright` | 1.63.0, 4.13.0 | development | pending approval |

**TypeScript 6.0.3, not 7.0.2:** `typescript-eslint` 8.71.0 supports TypeScript below 6.1.0. With TypeScript 7.0.2, lint would run on an unsupported compiler. If lint is not approved, TypeScript 7.0.2 is possible; verify it in the scaffold step.

`@testing-library/dom` is a required peer of `@testing-library/react`. Install checks (`npm ci`, `npm audit`, peer warnings) have not run. Record their results in the scaffold step.

### Folder structure

```text
frontend/
  index.html                 Google Fonts link, root element
  vite.config.ts             React plugin, /api proxy, test config
  playwright.config.ts
  public/brand/              four logo PNGs from the handoff copy
  src/
    main.tsx                 providers: QueryClient, Router, Session
    styles/tokens.css        all handoff tokens as custom properties
    styles/base.css          reset, focus outline, reduced motion
    lib/decimal.ts           exact decimal strings (scaled BigInt)
    lib/dates.ts             calendar dates and UTC event times
    lib/ids.ts               short IDs, Run #N
    api/client.ts            fetch wrapper, problems, headers
    api/types.ts             contract types, hand-written from docs/openapi.json
    api/endpoints.ts         one typed function per endpoint
    api/queryKeys.ts
    session/session.ts       sessionStorage, expiry timer
    session/SessionProvider.tsx
    session/capabilities.ts  route → capability map
    components/controls/     Button, Segmented, Tabs, Switch, Field, ShortId
    components/feedback/     StatusBadge, MissingChip, Callout, Toast, states
    components/overlay/      Dialog, focus trap
    shell/                   AppShell, Sidebar, ContextBar, Drawer
    pages/signin/  pages/unavailable/  pages/dashboard/  pages/catalog/
    pages/sql/     pages/refresh/      pages/settings/
  tests/e2e/                 Playwright specs
```

Types are written by hand from `docs/openapi.json`. A type generator would be another package. One unit test compares the hand-written enums with the OpenAPI file, so a later contract change fails the test.

### Routes

| Path | Page | Capability (R09) |
|---|---|---|
| `/sign-in` | Sign-in | public |
| `/` | Landing redirect from `landing_screen` (R10) | signed in |
| `/waiting` | Unavailable (A2) | signed in |
| `/dashboard` | National dashboard | `national:read` |
| `/catalog` | Catalog | `preview:detail` |
| `/catalog/:datasetKey` | Table view | `preview:detail` |
| `/sql` | SQL Explorer | `sql:execute` |
| `/refresh` | Run list | `refresh:read` |
| `/refresh/:runId` | Run detail and candidate | `refresh:read` |
| `/settings` | Schedule | `settings:read` |
| `/setup` | Initial setup | `settings:write` |

One `RequireCapability` element wraps each guarded route. It renders a redirect before the page mounts, so no page query starts (S03). The sidebar uses the same map.

### Session

- `session.ts` stores `{access_token, expires_at}` under one `sessionStorage` key. Every access is wrapped in `try/catch`. If storage fails, the session lives in memory for that page view.
- At start-up, a stored token whose `expires_at` has not passed is checked with `GET /me` before any page renders. On `401`, the session is cleared.
- A timer fires at `expires_at` and clears the session (R11). The server remains the authority.
- One function clears the session: it removes the key, clears the React Query cache and goes to `/sign-in` with a reason. Sign-out, `401` and expiry all call it.
- The token is read only by `api/client.ts`. It is never put in a URL, a log, an error message or React Query keys.
- Risk: any script on the page origin can read `sessionStorage`. Mitigation: no third-party scripts, no `dangerouslySetInnerHTML`, and no raw HTML from the API. A Content-Security-Policy belongs to hosting, which is out of scope. Record it as a hosting requirement.

### API client

- `request(method, path, {query, body, ifMatch, idempotencyKey})` builds a relative `/api/v1` URL with `URLSearchParams`. Body is JSON. Commands with no fields send `{}`. The warning DELETE sends no body.
- Success: returns `{data, etag, location, requestId}`.
- Failure: parses `application/problem+json` into `ApiError {status, code, detail, requestId, retryAfter, blocker, currentRevision}`. A non-JSON error becomes `internal_error` with the request ID.
- `401` calls the session clear function once and throws.
- React Query never retries 4xx errors. It retries a network failure at most twice for GET requests.
- **Idempotency:** a command object holds one key from `crypto.randomUUID()`. It is created when the user confirms, and reused if the same request is retried after a network failure. A new click makes a new object (R47).
- **ETag:** the hooks for settings, run and candidate keep the latest `etag`. Commands pass it as `If-Match`. On `412`, the hook refetches and the page shows the R52/R56 message.

### Query keys and refresh rules

| Key | Data |
|---|---|
| `['me']` | `/me` |
| `['catalog']` | `/catalog` |
| `['dashboard', range]` | dashboard |
| `['preview', key, filters]` | infinite query, pages by `next_cursor` |
| `['facilities', key, search]` | facility choices |
| `['runs']`, `['run', id]`, `['candidate', versionId]` | refresh |
| `['settings']`, `['schedule-status']` | settings |

- **Publication watch:** the API client reads `publication.publication_event_id` from every analytical response. When it changes, the client invalidates `me`, `catalog`, `dashboard` and `preview` (R31, R54).
- **Polling:** `['run', id]` sets `refetchInterval` to `poll_after_seconds × 1000`, or turns it off when the value is null (R49).
- `409 publication_changed` on a preview page resets that infinite query (R37).

### Decimal and date rules

- `decimal.ts` parses `-?digits(.digits)?` into `{value: bigint, scale}`. It supports add, multiply by 100, and divide rounded half-up to N places. `format` adds thousands separators and fixes the decimal places. A string it cannot parse is an error, never `NaN`. No `Number()` conversion of measurements anywhere; a lint rule bans `parseFloat` and `Number(` in `src/` outside `lib/` tests.
- Share = `outage × 100 ÷ capacity`, rounded half-up to 2 places. Capacity `0` gives null with reason `zero_capacity`. The combined share sums outage and capacity first (R17, R38).
- `dates.ts` keeps `YYYY-MM-DD` as strings. Day arithmetic converts to a UTC day number with `Date.UTC` and back. Display uses fixed month names, not the browser time zone (R19). Event times are formatted in UTC.

### Chart

- One SVG component, `NationalChart`, takes `days`, a domain `{x0, x1, y0, y1}`, the hover index and the pinned date.
- **X axis:** the day number. **Y axis:** shares, padded and rounded to steps of 5, 10 or 25.
- **Line:** null days split it into segments. A segment with one point draws a 6px dot. Gaps draw a hatched `<rect>` with dashed sides. Out-of-range points draw the ringed dot (R18, R26).
- **Range morph:** a `requestAnimationFrame` loop interpolates the domain for 650ms with ease-out cubic. Hover and pin are hidden during the morph. Under reduced motion, the domain jumps to its final value.
- **Keyboard:** the plot is focusable (`tabIndex=0`, `role="application"` with an `aria-label`). ←/→ move, Enter pins, Esc clears. An `aria-live` text states the date and values.
- **Sparkline:** a smaller version of the same parts, without interaction.
- **Daily values table:** reads the same `days` array, so chart and table values always agree (R27).

### Styling and motion

- `tokens.css` holds every handoff token. Components use CSS Modules (`*.module.css`), which Vite supports without a package.
- Motion uses CSS transitions and the Web Animations API with the handoff durations and curves. One `@media (prefers-reduced-motion: reduce)` block turns off transitions and animations. JavaScript animations check `matchMedia` before they start (R62).
- Below 960px the sidebar becomes a drawer. A focus trap is written in the `Dialog`/`Drawer` components (about 40 lines), with no package.

### Page notes

- **Sign-in:** no "Continue as" buttons. The account hint line stays, without passwords.
- **Catalog and tables:** filters are kept in a React context keyed by dataset, so they survive navigation in the session (R34). Until the facility list endpoint exists, the facility filter is an exact-ID text input.
- **SQL:** the editor is a `<textarea>` with a line-number gutter that follows its scroll position. There is no syntax highlighting, so no editor package. The example queries are fixed strings checked against SQL D01.
- **Refresh:** the steps list groups attempts by stage. The candidate panel loads only when `run.candidate` is not null.
- **Settings:** the time zone list comes from `Intl.supportedValuesOf('timeZone')`.

### Backend work in this branch

Each item uses the contract that already exists. It adds no new fields. Each one needs its own backend tests (offline and disposable PostgreSQL) under the existing runners.

| Item | Contract | Notes |
|---|---|---|
| `GET /dashboard/national`, `GET /metrics/offline-share` | API contract "Catalog and national dashboard" | Reuses the preview runtime path for the national dataset. Exact decimal share, null display points, 366-day limit. |
| `PUT /settings`, `GET /settings/schedule-status` | "Setup and daily schedule" | `If-Match` compare-and-swap, one-time setup, blocker order. |
| Facility and generator choices | "Preview and filter choices" | Analyst/Admin only, cursor bound to search and parent. |
| Rerun, delete warning | "Commands and concurrency" | `Idempotency-Key`, `If-Match: "run-<revision>"`, atomic slot handling. |

Before each backend item, write a short bounded design note in its task step and get alayala's approval, as for the earlier slices.

### Verification

| Level | Tool | What it proves |
|---|---|---|
| O, unit | Vitest | decimal, dates, IDs, client error mapping, session clear, capability map, OpenAPI enum agreement |
| O, component | Vitest + Testing Library, `fetch` replaced by a test stub | page states, guards, dialogs, keyboard, D02–D04 copy |
| R, real API | Playwright against Docker Compose with seeded personas | sign-in, landing, guards, sign-out, no-publication states, SQL denial for Viewer, refresh start |
| R, data | Playwright with a local publication | dashboard, tables, SQL results, review. Blocked until a publication exists locally (see open items) |
| H | alayala | screenshots compared with the handoff at 1440px and 924px |
| Accessibility | `@axe-core/playwright` plus a keyboard-only pass | S23 |

Tests that replace `fetch` are O evidence only. They never count as R evidence.

### Open items

- **Local publication for R data tests:** a synthetic publication made by the existing backend test helpers, or a recorded local refresh. Decide before step 7. Synthetic values are not EIA evidence.
- **Hosting headers:** CSP and the production origin are hosting work, out of scope.
- **Node version:** local Node is v26.3.0, and Vite 8.3.2 accepts `>=22.12.0`. The proposal pins 24.21.0 LTS for repeatable installs.

### Continuation design — steps 7–9

Implementation request: alayala asked to continue and finish steps 3–9. The
following implementation uses the existing API contract. It introduces no new
production package or retained-data migration. Earlier per-step starts are
covered by this continuation request; human visual acceptance remains separate.

- National reads reuse `PreviewService` authorization, shared admission, frozen
  publication evidence and isolated national-only execution. The service pins
  safe refresh metadata in the same publication snapshot. A complete national
  page contains at most 366 rows. The API builds calendar gaps and calculates
  exact decimal shares only after execution cleanup. The UI uses range-end
  cards as specified in R24; the earlier latest-card proposal is not adopted.
- Settings writes hold the shared lifecycle lock, recheck Admin authority, and
  compare the settings revision. Setup time is set once. No save enqueues work.
  Schedule calculations select the first repeated local occurrence and skip
  nonexistent local times. A scheduler role polls once per second, admits only
  crossed future occurrences, skips missed or blocked work, and uses a stable
  occurrence key to prevent duplicate outbox admission. It loads no EIA key.
- Choice endpoints must use bounded isolated execution and publication-bound
  cursors. They must not scan unbounded preview pages in the API process.
  Recovery must lock control, reauthorize, replay the same intent before stale
  revision checks, prove the old writer stopped, and retain every history row.
- Automated data checks use synthetic disposable state, never the retained
  publication or a live EIA refresh. Human persona and visual checks remain
  unchecked until observed.
