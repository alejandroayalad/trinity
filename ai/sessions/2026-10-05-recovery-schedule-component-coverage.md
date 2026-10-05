# Recovery and schedule component coverage

## Objective and contributions

[ME] Prioritized S20 positive recovery and S21 schedule page behavior; requested
no additional S14 work unless the task required a missing assertion.
[YOU] Added eight component tests in `frontend/src/pages/pages.test.tsx` on
`frontend`. Existing browser assertions cover exact `001a` and Generator gating.
No production code or dependencies changed. A16/A19/A20 and frontend R47/R53–R58
remain the behavior contracts. Design attribution remains in [NOTES](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026).

## Flow and checks

Recovery fixtures expose one enabled action. The test clicks its confirmation,
checks POST rerun versus bodyless DELETE warning, exact If-Match and a UUID
Idempotency-Key, and requires subsequent run and `/me` reads. Rerun displays the
replacement run; warning resolution removes the action from the original run.
Backend tracing corrected the fixture: warning resolution retains `failed`
history rather than changing it to `superseded`.

Schedule tests enter through Admin navigation or setup landing, render existing
values, edit all three fields, inspect PUT and If-Match, and verify saved values,
disabled Save, refreshed status, or setup navigation to Refresh. Four role/route
cases prove Viewer and Analyst cannot mount setup/settings or request their data.
Existing stale-revision coverage remains unchanged.

## Verification and limits

Node 24.21.0: full frontend suite passed, 77 tests in 9 files. The first typecheck
found unsupported Testing Library `exact` options on role queries; removed them
because string role names already match exactly. Final typecheck and lint passed. The final focused page suite passed 22 tests.
Diff whitespace and the new evidence links passed checks.
These tests stub fetch and provide offline component evidence, not real-backend
or browser recovery evidence. Backend/browser suites and production build were
not run for this test-only change. No live service, EIA request, commit or push.

Done: positive component coverage for S20 and S21.
Pending: real-browser recovery and extended schedule editing; human visual review.
Blocker: none for the component scope; combined acceptance rows remain open.

Next action: verify recovery through the disposable real-browser harness.
