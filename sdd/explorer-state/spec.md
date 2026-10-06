# Explorer state — bounded implementation

Authorized October 6, 2026. Original report IDs: QA-02, QA-04, QA-05,
QA-08, QA-06 (analytical recovery only). The supplied report is absent from
`frontend/test-results/live-qa-2026-10-06/`; parent-workspace filename search
also found no copy. The user prompt supplies the scope. The older
`qa-01-request-handling` name does not refer to the original logout finding.

## Scope and design

Extend existing TanStack Query observers, AbortSignal endpoints and bounded
429 retry. No backend, auth, permissions, contracts or Admin mutations change.
Search waits 300 ms after the last edit. Draft changes detach obsolete queries
immediately; only settled terms fetch. Infinite queries belong to one filter
visit so a revisit cannot replay old cursors. Reset remounts choice controls,
cancels timers, clears dates/IDs and closes lists. Linked IDs remain exact.
Generator lists load on open, after preview settles, avoiding competing reads.
Dashboard retains prior data with a persistent live status and busy region;
dependent analytical reads pause while the range updates. Retry uses current
parameters, disables duplicate actions and honors Retry-After. Publication
changes restart pagination without combining versions.

## Tasks and acceptance

1. Maintain data evidence — ongoing. No new EIA retrieval or anomaly claims.
2. Implement debounce, independent pagination visits and complete Reset.
3. Add dashboard status and bounded analytical recovery.
4. Prove races, cached revisits, Load all cancellation, retries, publication
   restart and Viewer isolation with controllable responses/timers.
5. Run typecheck, lint, tests and available targeted browser checks. Keep prior
   QA artifacts. Build and human acceptance remain [ME] work.

Acceptance: only the latest filters render; intermediate search terms do not
fetch; Reset cannot resurrect search; revisits start with one page; obsolete
Load all stops; loading/completion are announced; recovery is current and
single-flight; forbidden/unavailable/publication changes stay distinct.
Browser aborts never establish server capacity release. Report live and
simulated evidence separately. Record results in the linked session record.

## Verification status

Implementation and focused acceptance tests complete. Typecheck/lint pass;
100 unit tests and two simulated browser tests pass. Live range/search/filter,
pagination Reset and prefiltered URL checks passed. Live request counts and
backend stop/capacity evidence remain open; QA-02 is partial. Build and human
acceptance remain [ME]. See the [session evidence](../../ai/sessions/2026-10-06-explorer-state-implementation.md).
