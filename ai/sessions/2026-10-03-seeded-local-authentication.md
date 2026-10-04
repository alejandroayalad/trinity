# Session — Seeded local authentication for the challenge

Date: October 3, 2026. Branch: `docs/backend-decisions-architecture`.

## Objective and contributions

[ME] Alayala requested rollback of the Clerk authentication decision, seeded local authentication for the challenge, unchanged server-side roles/permissions, and Clerk documented as future production work. He requested documentation edits only. He discarded the preceding query/worker simplification.

[YOU] AI inspected repository status, current decisions, API/security/backend/schema documentation and the latest supporting security session. The initial working tree was clean. AI recorded A20, marked A8 superseded while retaining its original rationale, removed the Clerk SDK from the challenge dependency selection, and aligned current documentation. Historical session records remain unchanged.

## Decisions and concrete flow

A20 changes authentication only. Seed one Viewer, Analyst and Admin account locally. Login verifies credentials and issues a server-owned session. Protected calls resolve the current local identity and role before the existing permission checks. Reject request-supplied roles/actors; authentication failure grants no access. Clerk is future production work behind `auth/service.py`, not an optional challenge mode or fallback.

A20 supersedes Clerk-specific parts of A8/A10/A11/A15/A17/A19. A9 gains local account/session storage and local actor references; A16/OpenAPI gain login/logout. Existing 20 product operations, persona permissions, SQL controls, publication checks and recovery remain selected. Per-query containers, BullMQ, Redis and job_outbox remain unchanged.

[YOU] Endpoint names/fields, opaque revocable bearer sessions, local account/session logical fields and the repeatable seed outline are AI-authored contract completion for the approved direction. Exact hashing library/parameters, session lifetime, browser token handling, login-throttle settings and runnable setup commands remain implementation details. No credentials or usable seed accounts were created.

## Evidence and corrections

The preceding read-only review extracted the supplied challenge PDF: page 5 permits simplified authentication and requires a seeded test user per persona; pages 3 and 7 require README-based local execution and test-user setup. The brief does not explicitly forbid external-service setup or establish automatic Gate failure for Clerk. Current A19 nevertheless required live Clerk session/role checks; token signature verification alone would not satisfy that rule. Local auth removes this provider setup dependency, not EIA or storage configuration.

The prior Clerk decision and reaffirmation remain historical in A8 and dated sessions. A20 records why the choice changed. Current README and contracts describe the new direction without claiming implementation. [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) were consulted for the local-auth controls; this is design evidence, not security validation.

## Checks and results

Passed: `git diff --check`; JSON parsing and structural checks for 22 operations, unique operation IDs and 375 resolved internal OpenAPI references; endpoint inventory and login field-table agreement; login-only public exception and bodyless logout response; 219 local Markdown links, 76 anchors, balanced fences and 20 unique decision IDs. Compared with HEAD: all 20 original API operations, role/authorization table, SQL and query-container sections, analytical limits and publication policy, A6/A7, analytical schema, FINDINGS and historical sessions are unchanged. Reviewed the documentation diff. Link checks cover tracked Markdown and this task's new session. Unrelated untracked `docs/sdd/` and connector planning notes appeared during the task and were left untouched. These are static checks, not running security or full OpenAPI-conformance tests. No application code, runtime authentication tests, database migrations, package installations, commits, push or remote changes were performed. `rg --files` searches for pyproject.toml, package.json, Makefile and test/lint/check files found no repository check runner. Full OpenAPI/JSON Schema validators are not installed in the current Python environment; structural checks do not claim full specification conformance.

## Open implementation details and next action

[YOU] Select and verify local password/session implementation settings when backend implementation is authorized. Preserve the same authorization rules across direct API calls and every persona. Working login, seed reruns, expiry/revocation, account changes, throttling and fresh-clone execution remain unverified.

[ME] Next: review A20's local authentication flow in `DECISIONS.md`.

## Authentication-only transfer onto current main

[ME] Alayala confirmed that the connector is already available, withdrew the connector SDD work and requested only the local-authentication changes in a separate worktree from main, using cherry-pick.

[YOU] Fetched origin and confirmed local/main and origin/main at `481d088`, the PR #4 connector merge. Removed the obsolete connector SDD paragraph from NOTES and moved the four untracked SDD documents plus their planning session to a recoverable local archive outside Git. The current A20 draft was committed separately as `baebf1d` and cherry-picked with source attribution into `docs/local-authentication-a20`. The separate remote `98ea8e4` draft was inspected but not selected: it uses different authentication table names and introduces defaults absent from A20. No history was rewritten and no remote branch was changed.

README and NOTES had conflicts because main now contains connector implementation/setup evidence. Resolution retains that evidence and adds only current local-authentication guidance. The earlier no-code/no-test statements above describe the original draft checkout, not current main. A20 remains design only; the existing connector is implemented, while its live fetch is pending.

Checks: JSON parsing, unique operation IDs, internal OpenAPI references, login-only public access, bodyless logout response, preservation of all 20 existing product paths, changed-document local links/anchors and whitespace checks passed. Backend files, dependency lockfile, FINDINGS and the existing connector session are unchanged from main. Runtime/authentication tests and live EIA requests were not run for this documentation-only transfer. No push, PR or merge was requested or performed.

Next: [ME] open the `trinity-local-authentication` worktree in the next session and review A20 before authentication implementation.
