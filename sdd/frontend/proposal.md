# Proposal: Trinity frontend delivery plan

Date: 2026-10-04
Status: Direction approved October 4, 2026, when alayala selected Q1 (React + TypeScript + Vite, [A26](../../DECISIONS.md#a26--frontend-stack)) and requested the [specification](spec.md). On October 5 he answered Q2–Q4 (below); approval covers React, TypeScript and Vite only. This does not authorize implementation, dependencies or backend changes.
Inspected branch/HEAD: `frontend`, first drafted at `eed2ab6` (same as `origin/main`); the Figma/brand handoff was later committed as `444795f`.
Basis: A16, A19, A20, A25 and the Viewer/SQL refinements in [DECISIONS.md](../../DECISIONS.md); [API contract](../../docs/api-contract.md); [data contract](../../docs/schema.md); [security contract](../../docs/security-contract.md).
Design input: the handoff package, copied to [docs/design-reference/2026-10-04-explorer-handoff/](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md) without `support.js`. Attribution follows [A25](../../DECISIONS.md#a25--figma-design-and-brand-handoff). The author of the HTML package is pending confirmation (Q2).

## Human

### Goal

Build the Trinity web interface from the handoff package. Keep alayala's layouts and flows and the supplied brand tokens. Connect every screen to the real `/api/v1` endpoints. The prototype's fixtures, regex SQL parser and role switch are references only. They are not delivered behavior.

### Pages and what each one needs

| Page (handoff section) | Roles | API it uses | Backend today |
|---|---|---|---|
| Sign-in (A) | public | `POST /auth/login`, `GET /me`, `POST /auth/logout` | Implemented |
| Unavailable state (A2) | all | `GET /me` (`data_ready`, `landing_screen`) | Implemented |
| National dashboard (B) | all | `GET /dashboard/national`, `GET /metrics/offline-share` | **Missing** |
| Facility contributions (B.4) | Analyst, Admin | `GET /datasets/facility_outages/preview` (one date) | Implemented |
| Catalog (C) | Analyst, Admin | `GET /catalog` | Implemented |
| Table view (C) | Analyst, Admin (Viewer: national only, no button) | `GET /datasets/{key}/preview` | Implemented |
| Plant filter (C) | Analyst, Admin | `GET /datasets/{key}/facilities`, `.../generators` | **Missing** |
| SQL Explorer (D) | Analyst, Admin | `POST /queries`, `GET /catalog` for the schema panel | Implemented |
| Refresh runs and detail (E) | Admin | `GET/POST /refresh-runs`, `GET /refresh-runs/{id}` | Implemented |
| Candidate review (E) | Admin | `GET /candidates/{id}`, `.../approval`, `.../discard`, `.../publication-retry` | Implemented |
| Failed-run recovery (not in mock) | Admin | `POST /refresh-runs/{id}/rerun`, `DELETE /refresh-runs/{id}/warning` | **Missing** |
| Schedule settings (F) | Admin | `GET/PUT /settings`, `GET /settings/schedule-status` | Only `GET /settings` |
| Initial setup (not in mock) | Admin | `PUT /settings` when `setup_completed_at` is null | **Missing** |

Evidence: routes found with a search for `@router.` in `backend/src/trinity/`. The backend has routers for auth, settings (GET only), catalog, queries (SQL and preview), refresh runs and candidates. It has no dashboard, metric, facility/generator choice, rerun, warning or settings-write route.

### Where the mockup and the contracts differ

The contracts take priority (A25). Each item needs a frontend choice. It does not change the API.

1. **Missing values.** In the mock, a facility row can have a `null` outage ("○ Not reported"). In the data contract, `capacity` and `outage` are never null. A missing observation is an absent row. Only the dashboard `days` array has null display points. Consequence: the table view cannot show "N rows not reported" from preview rows. It can show only the rows that exist. The facility list and sparkline must show absent rows as "Not reported".
2. **Names and IDs.** The mock uses `facility_name` and filters by plant name. The schema uses `facility` (source ID, the key) and `facilityName` (optional label), and the API filters by exact ID. The Plant filter shows the name but sends the ID. The SQL schema panel uses columns from `GET /catalog`, not a fixed list.
3. **Viewer and facility data.** The mock shows facility contributions on the dashboard. Viewer has national-only data access. Show contributions only to Analyst and Admin.
4. **Aggregate footer.** "Σoutage ÷ Σcapacity" is correct only for all matching rows. Preview pages have at most 1,000 rows. Show the footer only when all rows are loaded (no `next_cursor`). Otherwise show "Load all rows to calculate". Use decimal arithmetic, not binary floats.
5. **IDs.** The mock shows `pub-2026-09-28-a`, `run-1044` and `ver-19c`. The API uses UUIDs and `run_seq`. Show a short mono form and the full value in a tooltip.
6. **Run steps.** The mock steps are Accepted → Retrieve → Prepare → Validate → Review. API stages are `extract`, `prepare`, `validate`, `publish` and `dispatch`. Map the labels; do not invent stages.
7. **Refresh commands.** `POST` commands need an `Idempotency-Key` UUID. Run pages poll at `poll_after_seconds` and stop when it is null.
8. **States not in the mock.** Initial setup, failed-run recovery (rerun / resolve warning), `429 rate_limited` with `Retry-After`, `409 publication_changed` for a preview cursor, and an expired session. Each needs a simple screen or message in the existing style.
9. **Prototype-only items.** Remove "Continue as …", the role switch, the data-state switch, the outcome selector and the "Illustrative data" tag. Keep them only behind a development flag if wanted.

### Proposed stack (Q1)

The handoff README assumes "the existing Trinity React (Vite) codebase". No `frontend/` folder exists. The frontend technology is still open (README, A25). Recommendation:

- **React + TypeScript + Vite.** It matches the handoff, and the prototype is already written as React components.
- **React Router** for pages and role guards. **TanStack Query** for API calls, polling and cache invalidation after publication.
- **Plain CSS with custom properties** for the tokens. The handoff gives exact values, so a CSS framework adds nothing.
- **Hand-built SVG chart.** The gap bands, keyboard pinning and range morph are custom; a chart library would fight them.
- **Vitest + Testing Library** for components; **Playwright** for role and flow checks against the local Docker API.
- Development: the Vite dev server proxies `/api` to `127.0.0.1:8000`. The browser sees one origin, so the backend needs no CORS change.
- Exact versions and a lockfile follow the A17 policy. Only React, TypeScript and Vite are approved; the other packages above are listed for approval in the [specification](spec.md#dependencies-pending-approval).

### Delivery slices (proposed order)

Order: first the pages whose backend exists, then each missing backend endpoint with its page.

| # | Slice | Depends on |
|---|---|---|
| F0 | Decisions: Q1–Q4, then spec/design/tasks for F1 | this proposal |
| F1 | Scaffold: `frontend/` app, tokens, fonts, logo assets, shell (sidebar, context bar, drawer under 960px), role-based navigation, API client, problem/error handling, dev proxy | Q1 |
| F2 | Sign-in, session, sign-out, unavailable state, landing redirect from `landing_screen` | F1 |
| F3 | Catalog and table views with filters, cursor pages, per-table filter memory | F2 |
| F4 | SQL Explorer: editor, ⌘/Ctrl+Enter, result states, schema panel | F2 |
| F5 | Refresh history, run detail with polling, candidate review, approve/discard dialogs | F2 |
| F6 | Backend: `GET /dashboard/national`, `GET /metrics/offline-share` | publication slice |
| F7 | National dashboard: KPIs, meter, chart with gaps, daily values, selected observation, contributions | F6, F3 |
| F8 | Backend + UI: `PUT /settings`, schedule status, initial setup, schedule page | F2 |
| F9 | Backend + UI: facility/generator choices (Plant filter), rerun and resolve warning | F3, F5 |
| F10 | Acceptance: direct-URL role checks, keyboard and screen-reader pass, reduced motion, 924px and 1440px screenshots compared with the handoff, evidence note | all |

Step 1 of every plan: **Maintain data evidence — ongoing.** The frontend shows data. It does not create findings. Mock values are not EIA evidence.

### Out of scope

Public hosting, Clerk, query history or export, editable roles, and any change to publication rules or permissions.

### Acceptance (whole frontend)

- Each page matches its handoff screenshot at 1440px and 924px.
- Viewer cannot reach Catalog, Table or SQL by link or by typing the URL. The server also denies the API call.
- Missing data is never shown as `0`. Out-of-range values are shown unchanged and flagged.
- Publication time, latest observation and selected date are always separate.
- A failed or unfinished run never changes the publication shown.
- All motion stops under `prefers-reduced-motion: reduce`.

## Open questions (one at a time)

- **Q1.** Select React + TypeScript + Vite with the stack above? **Accepted October 4, 2026 (A26).**
- **Q2.** Who made `Trinity.dc.html` and its README? **Answered October 5: pending confirmation in A25.** Do not attribute them to a tool without evidence. Alayala reported that design images and prompts were generated in a Codex chat.
- **Q3.** (Now spec D01.) **Answered October 5: `sessionStorage`** (after correcting an earlier memory-only answer). Original question: Browser token storage: memory only (sign in again after a reload) or `sessionStorage` (survives a reload, cleared when the tab closes)? Recommendation: `sessionStorage`, with `Authorization: Bearer` only, never a URL parameter.
- **Q4.** Copy the handoff package into `docs/design-reference/` so the repository holds the reference? **Answered October 5: yes, without `support.js`; originals kept; provenance and exclusions documented.**
