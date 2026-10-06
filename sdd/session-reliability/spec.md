# Session reliability — original QA-01, QA-09 and startup QA-06

Authorized October 6, 2026. This is not the older request-handling slice's QA-01.
The original QA report remains absent; the user supplied these issue IDs/scope.

## Scope and design

Preserve A20 local sessions, server role authority and A16 logout semantics.
Logout sends the current token once and immediately clears local session/cache.
Show pending confirmation, then confirmed revocation for 204, an already invalid
session for 401, or an explicit unconfirmed-revocation warning for other failures.
Do not retain the token or automatically retry the POST. Failed revocation may
leave the server session valid until expiry; local sign-out is not server proof.

Share one in-flight /me promise per provider/session generation. StrictMode
replay and concurrent refresh callers share it; later checks remain fresh.
Startup failure keeps protected pages unmounted and offers manual Retry on both
protected and sign-in routes. Existing read Retry respects Retry-After. Invalid
sessions clear local authority; late old responses cannot reopen or clear a newer
session. A response after local sign-out cannot replace the revocation warning.

## Tasks and acceptance

1. Maintain data evidence — ongoing. No data retrieval in this slice.
2. Distinguish local logout from confirmed server revocation.
3. Deduplicate only in-flight authority checks and expose startup Retry.
4. Test StrictMode, network/503/401, pending/duplicate actions, cache clearing,
   expired/new sessions, stale replies, and browser behavior with simulated errors.
5. Run typecheck/lint/tests and isolated browser regressions; preserve old artifacts.

No backend, session lifetime, permission, Admin-command or API-schema changes.
[ME] retains build and human acceptance. No retained credentials or sessions are
used for simulated browser tests; no live logout is induced by the agent.

## Verification result

Typecheck and lint passed. All 128 unit tests and four isolated Playwright tests
passed. Browser transport failures were simulated; the logout warning screenshot
was inspected. No build or real server revocation failure was exercised.
See [session evidence](../../ai/sessions/2026-10-06-session-reliability.md).
