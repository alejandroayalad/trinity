# Session — QA-01 request handling implementation

Date: 2026-10-05
Mode: Implementation. [ME] alayala requested a small SDD cycle for QA-01, then said "implement the slice".
Basis: [proposal](../sdd/qa-01-request-handling/proposal.md), [spec](../sdd/qa-01-request-handling/spec.md), [design](../sdd/qa-01-request-handling/design.md), [tasks](../sdd/qa-01-request-handling/tasks.md), QA-01.

## Objective

Fix request handling behind QA-01: the last choice wins, cancelled work releases server capacity, Catalog dates need Apply, transient failures have a Retry, and `/facilities` loads only when opened.

## Contributions

- [ME] Reported QA-01 with reproduction steps, evidence and a proposed fix. Authorized the implementation.
- [YOU] Claude (OpenCode) traced the frontend and backend paths, wrote the SDD records, implemented the client changes and the tests, and ran the checks below.

## Design correction from tracing

The QA-01 fix proposal suggested server-side work. Tracing showed the backend already stops a disconnected analytical request: `supervised_call` in `backend/src/trinity/queries/router.py` polls `request.is_disconnected()` every 0.1 s, and `QueryExecution.execute` in `backend/src/trinity/queries/client.py` kills the container and releases the reservation in `finally`. The safe rule in `docs/security-contract.md` L82 forbids releasing a slot on the HTTP end alone. The defect is client-side: the typed endpoint functions never passed a cancel signal. No backend source file was changed. A later review added one regression test, `test_disconnect_while_container_runs_ends_it_and_releases_capacity` in `backend/tests/test_preview_lifecycle.py`. The uncommitted backend changes in the working tree were left untouched.

## Assumption accepted with the plan

R4: one automatic retry, only for `429 rate_limited` with `Retry-After` ≤ 5 seconds. Longer or missing waits show the Retry button. This protects the 30 requests/minute budget in `reserve_rate`.

## Checks and results

- `npm run typecheck` — passed.
- `npm run lint` — passed, 0 warnings.
- `npm test` — 85 passed in 10 files. The 7 new checks are in `frontend/src/pages/qa01.test.tsx`.
- Playwright `rapid dashboard preset clicks` against the retained API — passed (8.8 s). It observes `preset=1y` and `preset=90d` requests fail with an abort, the 30-day button active, zero 429 responses, and no error text.
- Playwright `Analyst loads published tables` — passed with `--timeout=90000` (22 s) after updating it for the lazy choice load and a publication-independent facility ID. The default 30 s test timeout is marginal against current live preview latency.
- Playwright `Viewer dashboard` — fails on its fixed `2026-07-06` date. The retained publication moved to a latest observation of 2026-10-05 after the test was written. Pre-existing data drift; not caused by and not fixed in this slice.

- Review pass (second OpenCode session): re-ran `npm run typecheck`, `npm run lint` and `npm test` (85 passed). Ran `test_preview_lifecycle.py`, `test_preview_service.py` and `test_dashboard_service.py` in a temporary environment outside the repository: 45 passed. The new backend test was not checked against a deliberately broken cancel path.

## Open questions

- The e2e suite pins real dates. It needs dynamic date derivation or a refresh per publication.
- Whether to raise the default e2e timeout for live preview latency.

## Next action

[ME] Reviews the diff and decides whether to commit. Suggested commit: `fix(frontend): cancel superseded dashboard and catalog requests`.
