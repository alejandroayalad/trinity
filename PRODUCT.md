# Trinity — Product scope

Status: selected scope, not implemented. Owner: alayala. Keep this note within one page when formatted for submission.

**Purpose:** Let people explore U.S. nuclear outage data locally, run permitted SQL, and understand differences between national, facility, and generator records.

**Core users:** Viewers see national trends only. Analysts explore all analytical datasets and run read-only SQL. Admins have Analyst access plus refresh and shared configuration controls.

## Committed product additions

| Story | Selected behavior |
|---|---|
| Refresh without waiting for an operator | Scheduled refreshes and manual Admin refreshes use the same validation process. |
| Configure the account once | An Admin sets the shared schedule during initial account setup. Default to daily with a selected time and timezone. Do not repeat setup for each Admin. |
| Control when new data becomes visible | Select automatic publication after validation or Admin approval after validation. Required failures block publication in either mode. |
| Change routine policy without developer support | Authorized Admins can edit the shared schedule and publication mode later. |
| Keep a usable dataset during refresh | Retain the last valid published version during preparation, pending approval, or failure. Show publication time, latest observation date, and refresh outcome. |

These are committed project features under A2–A3. Arkham did not explicitly require the initial setup flow or both publication modes.

## Interface choices and limits

Use a short initial configuration flow and one shared settings area. Distinguish fetching data from publishing it. Before the first valid publication, show that data is unavailable. A manual refresh is different from reloading the dashboard.

Separate organization accounts and a new registration flow are outside the selected scope. Charts, export, SQL autocomplete, and query history are not committed features. Detailed visual design and framework choices remain open.

## Data behavior and next implementation

The [v1 data contract](docs/schema.md) now specifies keys, same-day capacity/outage metrics, missing observations, validation, and publication. It preserves the selected flows above. Choose the runtime stack and build the first verified data slice. Further product additions are not selected.

Sources: [DECISIONS.md](DECISIONS.md), A2–A4; `Software Engineer - Technical Challenge.pdf`, pages 2 and 6.
