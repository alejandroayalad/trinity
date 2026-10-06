# Session reliability — October 6, 2026

## Objective and contributions

[ME] Alayala requested committing/pushing the completed presentation slice,
then implementing original-report QA-01, QA-09 and startup QA-06.
[YOU] Codex pushed presentation implementation `793364d` and evidence `4daaddc`,
then implemented and verified this separate session slice. Session changes are
uncommitted. Concurrent backend, Compose and documentation work was preserved;
concurrent QA-03 commit `9b2a4b3` was observed without modification.

The original `frontend/test-results/live-qa-2026-10-06/REPORT.md` was absent from
the checkout and the parent-workspace search. Issue IDs follow the user's scope,
not `sdd/qa-01-request-handling` numbering. Relevant authority: A19/A20,
`docs/api-contract.md`, `docs/security-contract.md`, and frontend D01/R07/R11/R12.
Scope/design/tasks/acceptance: `sdd/session-reliability/spec.md`.

## Findings and corrections

### QA-01 — logout reliability: fixed in frontend; live acceptance pending

- Severity/scope: authentication feedback, frontend.
- Expected: distinguish immediate local sign-out from server-confirmed revocation.
- Observed: the prior logout path cleared local state while suppressing POST failure.
- Evidence/flow: `SessionProvider.signOut` sent logout and cleared local state;
  its failure did not produce a distinct warning on `SignIn`.
- Failure scenario: server returns 503 or network fails; the token disappears
  locally but the server session can remain valid while the UI implies success.
- Correction: send once, clear local token/private cache immediately, show pending
  confirmation, then distinguish 204, 401 and unconfirmed failure. Announce the
  warning with role=alert. Block sign-in during confirmation; never replay POST.
- Validation still required: real server write failure and operator acceptance.

### QA-09 — duplicate startup authority checks: fixed in simulated verification

- Severity/scope: startup coordination, frontend.
- Expected: concurrent startup consumers share one in-flight /me check.
- Observed: StrictMode effect replay independently invoked `refresh` twice.
- Evidence/flow: each startup effect called `getMe`; no in-flight sharing existed.
- Failure scenario: initial mount starts competing reads before either completes.
- Correction: `SessionProvider.refresh` shares only the current generation's
  pending promise. Later authority checks remain fresh. Generation checks ignore
  old responses; the API 401 handler only ends the matching current token.
- Validation still required: retained browser network acceptance.

### Startup QA-06 — recovery: fixed in simulated verification

- Severity/scope: startup availability, frontend.
- Expected: recoverable startup failure offers Retry without protected content.
- Observed: startup error views had no retry action.
- Evidence/flow: `Guard` rendered the failure; `SignIn` lacked startup recovery.
- Failure scenario: temporary /me 503 leaves the user unable to recover that view.
- Correction: both routes use shared `PageError` and `retryStartup`; Retry-After,
  active-operation guard and in-flight sharing bound manual recovery. A 401 ends
  the session. Delayed responses cannot reopen or clear replacement sessions.
- Validation still required: real temporary auth-storage failure and human checks.

## Files and verification

Implementation: `frontend/src/session/SessionProvider.tsx`,
`frontend/src/session/capabilities.tsx`, `frontend/src/api/client.ts`, and
`frontend/src/pages/signin/SignIn.tsx`. Regression tests:
`frontend/src/session/session.test.tsx` and
`frontend/tests/e2e/session-reliability.{spec,config}.ts`.

- `npm run typecheck`: passed.
- `npm run lint`: passed, zero warnings.
- `npm test`: 128 tests passed in 12 files.
- `npx playwright test --config tests/e2e/session-reliability.config.ts`:
  four passed against running Vite; all auth transport was simulated.
- `git diff --check`: passed; scoped source diff reviewed.

Unit tests cover StrictMode, duplicate Retry, expiry, current 401, late replies,
replacement login, cache clearing, network/503 failures and confirmed logout.
Browser counts: one initial /me and one manual retry; one logout POST in each
failure case. No protected navigation appeared during startup failure or after
logout. Retry-After disabled Retry until eligible. Server-failure warning screenshot
was visually inspected and readable. Browser clock-control attempts timed out;
the final test uses Playwright's enabled-state wait, with no arbitrary sleep.

Artifacts remain isolated in
`frontend/test-results/session-reliability-2026-10-06/`, including JSON results
and two synthetic-session screenshots. Prior QA artifacts were preserved.
No credentials, retained logout, backend edits, dependency changes or builds were
used. Simulations do not prove backend revocation, real capacity or retained
readiness. Console health under real auth failure was not verified.

## Checkpoint

Done: presentation pushed; session implementation and automated checks complete.
Pending: human build/acceptance and retained auth-failure verification.
Blocker: none for frontend implementation; original QA report unavailable.
Next [ME]: open http://127.0.0.1:5173/dashboard to inspect the running frontend.
