# Full-system live acceptance plan

Status: planned, not executed. October 4, 2026.

[ME] Alayala requested focused implementation commits and push first, followed by
planning the entire live EIA → Refresh → Publication → Catalog/Preview/SQL test.
This request does not start cloud writes, retained migrations or live activation.
[YOU] prepared this plan from current source and the
[Publication acceptance record](../ai/sessions/2026-10-04-publication-implementation-acceptance.md).

## Target and current gaps

Run the actual HTTP API and background processes against live EIA and application-owned
S3. Use a dedicated acceptance database, Redis namespace, private worker root and S3
prefix. Preserve existing retained data and services. Carry one real run/version/event
identity through every stage; do not insert an event or pointer to simulate success.

Current source establishes these prerequisites:

- `settings.router` exposes only GET settings. Setup/schedule writes are absent;
  Run again and warning deletion remain deferred. Seeded setup in an isolated test
  database can exercise the implemented pipeline, but cannot count as product setup
  acceptance. Whole-product completion requires separately scoped implementation.
- `refresh.repository.reserve_run` fixes the requested start at **2024-10-02**;
  `RefreshWorker._discover` selects the live end. The HTTP request accepts no date
  override. This is a full historical refresh, not the earlier October 1–2 proof.
  Measure expected volume, deadlines and cost before execution. Do not silently
  narrow the production policy or bypass it through manual run inserts.
- `compose.yaml` supplies API/PostgreSQL; `compose.sql.yaml` adds query configuration.
  Neither launches the complete Redis/Refresh/Publication worker topology. Prepare
  explicit isolated process configuration before claiming a running full system.
- Fresh `uv sync --locked`, actual worker-root custody, S3 overwrite/delete protection
  and published-reader access still need evidence. Existing synthetic tests and CLI
  login alone do not prove these dependencies.

## Sequence and exit gates

### 1. Maintain data evidence — ongoing

[YOU] Review FINDINGS, the frozen October 1–2 evidence and the full-window policy.
List every product slice as implemented, missing or awaiting live proof. Record the
planned dataset/window, expected keys/coverage and an independent comparison method.
Keep AN-01–AN-03 and unresolved candidates intact. New observations follow AGENTS.md.

Exit: a coverage matrix with no missing feature silently marked tested. Separate
the implemented-pipeline verdict from the whole-product verdict.

### 2. Prepare an isolated real-service environment

[YOU] Inventory versions/configuration without printing secrets; provide exact scoped
startup and migration commands. [ME] select the acceptance S3 prefix and authorize
cloud writes/activation, the historical window/cost and any setup prerequisite.
[ME] run commands involving the EIA key, builds and evaluator-owned setup.

Install from the lockfile in a fresh environment. Apply migrations to the dedicated
database and seed local personas. Configure distinct cursor keys, worker root, Redis,
writer/read credentials, query image digest, staging volume and Docker access.
Run the repository's offline, database, Redis and actual-container checks against
the pushed revision. Start API, Refresh outbox/worker/recovery and Publication
outbox/worker on the supported single host. Record readiness for each process.

Exit: all dependencies pass, no required test is skipped, secrets stay private and
the exact setup gap is resolved or explicitly blocks whole-product acceptance.

### 3. Execute one continuous live refresh and read it

[ME] sign in as Admin and start Refresh through the real HTTP command. [YOU] follow
its receipt, outbox, discovery, pagination, extraction, Parquet, required checks,
diagnostics and exact S3 readback. Record row/date/key coverage for all three datasets.
Required failure or incomplete data must remain unpublished; diagnose without waivers.

If warnings occur, inspect the real frozen candidate and use the Admin approval
command. Otherwise verify automatic publication. Confirm exactly one committed event,
the active pointer, successful run/step and released admission slot. Compare S3 bytes
and hashes independently with the saved manifest/receipt.

Use actual Viewer, Analyst and Admin sessions. Verify login/logout/revocation, `/me`,
settings permissions, Catalog freshness and dataset access, Preview filters/pages/
diagnostics and allowed SQL. Compare SQL counts, dates, sums and weighted metrics
with independent calculations from the same saved files. Exercise denied datasets,
disallowed SQL and app-state/unpublished-file isolation. Verify query containers use
only authorized files, have no network, enforce bounds and clean up.

Exit: one trace connects live source → stored bytes → committed publication → real
HTTP reader results for every implemented slice. No direct database publication.

### 4. Exercise switching and recovery without damaging retained data

Run a second real refresh in the acceptance environment. Keep SQL/Preview requests
in flight across activation; prove old files/diagnostics stay pinned, new requests
use the new event and old cursors reject with `publication_changed`.

Use separately isolated acceptance candidates for controlled worker stops, temporary
storage unavailability and discard. Invoke the real recovery CLI, then Admin retry;
verify fresh byte checks, original approval attribution and one invocation per
generation. Confirm the old publication remains usable and unsafe work stays blocked.
Never corrupt or delete retained evidence to manufacture a failure. Keep synthetic
fault injection results distinct from live-source proof. If live data produces no
warnings, report that the live approval path was not exercised; do not alter source
values to force it. Test schedule/setup through product commands only once implemented.

Exit: recovery, repeat requests, role boundaries and second-publication behavior have
measured results, with unexercised branches visible.

### 5. Close the acceptance matrix

[YOU] Record pushed revision, dependency/image versions, sanitized commands, run/version/
event IDs, UTC times, coverage, hashes, persona outcomes and each expected/actual result.
Classify each slice as passed, failed, blocked or not implemented. Separate offline,
synthetic service, live-source, cloud-storage and human-operated evidence.

Do not declare the whole system complete while a required feature or gate is missing.
Keep full-history capacity, schedule/setup, frontend (if required for the submission)
and deployment claims explicit. Cleanup targets only named acceptance resources after
evidence retention is agreed; no retained data deletion or downgrade.

## Next action

[YOU] Complete a read-only readiness inventory at the pushed revision and present
the missing setup/schedule scope plus the exact isolated live execution configuration.
No live run has started under this plan.
