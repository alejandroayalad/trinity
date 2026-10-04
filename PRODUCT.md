# Trinity — Product scope

Status: selected scope, not implemented. Owner: alayala. Keep this note within one page when formatted for submission.

**Purpose:** Let people explore U.S. nuclear outage data locally, run permitted SQL, and understand differences between national, facility, and generator records.

**Login:** Seeded local accounts for the three personas under A20. Clerk is deferred production work. Authentication must preserve all server-side permission checks.

**Core users:** Viewers see national trends only. Analysts explore all analytical datasets and run read-only SQL. Admins have Analyst access plus refresh and shared configuration controls.

## Committed product additions

| Story | Selected behavior |
|---|---|
| Refresh without waiting for an operator | Scheduled refreshes and manual Admin refreshes use the same validation process. |
| Configure the account once | An Admin sets the shared schedule during initial account setup. Default to daily with a selected time and timezone. Do not repeat setup for each Admin. |
| Control when new data becomes visible | Publish automatically after required checks pass without warnings; require Admin review when warnings remain. Failed/incomplete checks block publication. |
| Change routine policy without developer support | Authorized Admins can edit schedule enabled, daily time and timezone. Publication behavior is fixed by A16. |
| Keep a usable dataset during refresh | Retain the last valid published version during preparation, pending approval, or failure. Show publication time, latest observation date, and refresh outcome. |

These are committed project features under A2–A3 as amended by A16. Setup and the detailed warning/recovery flow are author-selected product behavior.

## Interface choices and limits

Use a short initial configuration flow and one shared settings area. Distinguish fetching data from publishing it. Before the first valid publication, show that data is unavailable. A manual refresh is different from reloading the dashboard.

A16 includes a national dashboard with summary cards, daily trends and table values; 30/90-day and yearly presets; filtered entity choices; and candidate review in a side panel on the run page. One refresh lifecycle is admitted at a time. Required review and unresolved failures block another refresh; Admin recovery preserves history and abandons candidates permanently when requested. Separate organizations, registration, export, SQL autocomplete and query history remain outside scope. Detailed visual styling and frontend framework remain open.

## Data behavior and next implementation

The [v1 data contract](docs/schema.md) now specifies keys, same-day capacity/outage metrics, missing observations, validation, and publication. A16 supplies the approved API flow and amends publication/recovery behavior; [the API contract](docs/api-contract.md) defines fields and examples. Implementation and runtime verification remain pending.

Sources: [DECISIONS.md](DECISIONS.md), A2–A4 and A16; `Software Engineer - Technical Challenge.pdf`, pages 2 and 6.
