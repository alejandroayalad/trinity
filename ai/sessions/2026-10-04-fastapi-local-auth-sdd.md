# FastAPI and local login — SDD drafting

Date: 2026-10-04 (America/Merida)
Branch: `feat/fastapi-local-auth`
Base: `17864ee`, local main at inspection. No remote refresh was performed.
Status: Four requested SDD drafts created; review and implementation remain pending.

## Objective and authorization

[ME] Alayala supplied the “FastAPI and login · 6:30–7:15” task, clarified local authentication replaces Clerk, and requested proposal, spec, design, tasks and a new branch. This request authorizes all four planning artifacts together. It does not claim their proposed defaults are approved or authorize code, migrations, account provisioning, builds, live services, commits, pushes or a PR.

[YOU] AI read repository instructions, README, PRODUCT, CONTRIBUTING, A10–A12/A15–A17/A19/A20, API/security/schema/backend contracts and OpenAPI shapes. Prior authentication and latest Parquet closure records supplied history; current code and Git state supplied the implementation baseline. AI used the existing Human/LLM SDD format. No subagents or additional skill were needed.

## Discovery and preservation

`git status --short --branch` showed main with unrelated changes to FINDINGS, NOTES, README and schema plus untracked findings scripts, tests and evidence. `git worktree list --porcelain` identified existing worktrees. AI used `git worktree add -b feat/fastapi-local-auth ../trinity-fastapi-local-auth HEAD` to isolate this task. The new branch starts from committed main, so unrelated local findings changes remain in the original worktree.

`create_app` in `backend/src/trinity/main.py` registers only health. `config.py` provides explicit EIA/S3 settings. `git ls-tree -r --name-only HEAD backend sdd` plus filesystem checks found no auth package, migration directory or errors module. Existing backend dependencies include the selected web/database stack; no password library is selected in A17. Auth, migrations and seeded users remain unimplemented.

## Drafts and decisions

[YOU] Created [proposal](../../sdd/fastapi-local-auth/proposal.md), [specification](../../sdd/fastapi-local-auth/spec.md), [design](../../sdd/fastapi-local-auth/design.md), and [tasks](../../sdd/fastapi-local-auth/tasks.md). Linked them from README and recorded authorship in NOTES. All proposed defaults remain reviewable drafts; DECISIONS and canonical contracts were not changed.

A20 governs local identities and revocable opaque sessions; A19 preserves backend permissions and fail-closed checks. A16/OpenAPI owns `/me`, readiness, landing screens and errors. The design proposes scrypt using Python primitives, an eight-hour session, PostgreSQL login throttling and a necessary app-entry migration dependency closure. It adds read-only settings within the planned slice for a real Admin-only HTTP check. No setup writes, SQL/query execution, refresh worker or publication action is claimed.

Correction: the supplied task's Clerk verification wording is superseded by A20. Direct API tests of `/me` alone cannot prove full role isolation. The spec distinguishes real login/me/settings route evidence from a test-only analytical permission harness and later product-route acceptance. No-data state remains distinct from a dependency outage. The 45-minute slot is not a completion guarantee.

Official references consulted for proposed cryptographic defaults: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [Python hashlib](https://docs.python.org/3/library/hashlib.html), [Python secrets](https://docs.python.org/3/library/secrets.html). These support the proposal; no compatibility or security-runtime result was obtained.

## Checks and results

Passed: local Markdown targets (137 links, including 26 anchors across seven changed/new documents), balanced fences, whitespace checks for tracked and untracked documents, unique R01–R13/S01–S24 identifiers, and agreement of the four planned product routes and 11-capability count with the canonical OpenAPI inventory. Reviewed the draft contents and the README/NOTES diff. These are static documentation checks, not full OpenAPI validation or proof that an endpoint exists.

Backend tests, PostgreSQL, persona provisioning, API execution and live EIA/S3 were not run because this change contains documentation only. Existing historical test counts are not new results. No code, dependency, lockfile, canonical contract, decision or findings file was changed in this worktree; no commit, push or remote mutation occurred.

## Open questions and next action

Review the proposed password/session/throttle defaults and migration scope before code. Exact PostgreSQL version/Compose image must be selected and pinned during the foundation step. Frontend token handling and full SQL/refresh endpoint acceptance remain later work. Maintain data evidence — ongoing; no new data observation was produced.

Done: four requested drafts and an isolated local branch.
Pending: human review, implementation authorization and all runtime acceptance scenarios.
Blocker: none for drafting; runtime correctness has not been established.

Next: [ME] read the Human section of the proposal.

## Subsequent implementation authorization

[ME] Alayala subsequently requested complete implementation, commit and push. This supersedes the draft-only authorization boundary above. [The separate implementation session](2026-10-04-fastapi-local-auth-implementation.md) records the completed code, measured checks, corrections and delivery. The original drafting record remains historical.
