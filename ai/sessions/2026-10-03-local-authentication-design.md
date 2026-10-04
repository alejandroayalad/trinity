# Session — Local authentication design amendment

Date: October 3, 2026 (America/Merida). Base: `main` at `3aa713fdec0f4913808c7de195024e7f2e381831`. Branch: `docs/local-authentication`.

## Objective and contributions

[ME] Alayala requested a focused design patch on a new branch from main, replacing Clerk with reproducible local login while preserving backend-enforced Viewer/Analyst/Admin permissions. He explicitly excluded unrelated SQL, S3, Redis/BullMQ, refresh and publication changes.

[YOU] AI read the current GitHub tree and contracts at the main commit. Direct Git clone lacked credentials; the connected GitHub API supplied the files. All 35 baseline file blobs matched their GitHub hashes before editing. The new remote branch was created at the requested main commit. AI drafted the local seed/session design and aligned the decisions, setup, backend, API/OpenAPI, security and schema notes. The field guide now describes local actor IDs. Historical session records remain unchanged.

## Explicit design changes

- Amend A8/A19 for three seeded PostgreSQL users, Argon2id password hashes and opaque server-stored sessions. Eight-hour expiry and other exact defaults are AI-authored completion details under the requested scope, not separately observed approvals.
- Add the logical `auth_users` and `auth_sessions` tables. Keep existing actor columns as text and preserve historical values. No migration has been implemented or executed.
- Add login/logout to the 20 product endpoints (22 total). Preserve bearer transport and server-side role checks; `GET /me` retains its product behavior.
- Remove the planned Clerk adapter/dependency/configuration. A maintained Argon2id implementation, exact package pin and parameters remain explicit implementation work. No manifests, lockfiles or environment files exist on this main baseline.
- Require an explicit repeatable seed command with environment passwords. No provider account, default password or automatic API-startup seeding is introduced.

## Corrections and verification

Review caught two documentation issues before delivery: the endpoint inventory still counted 20 after adding auth, and the first draft used a validation error name absent from the existing contract. Both were corrected. Shared authentication error responses keep the OpenAPI patch focused.

Checks passed: 22 unique OpenAPI operations; all 20 original product operations unchanged apart from the synthetic user ID; 383 internal schema references resolved; login is the sole authentication exemption; 222 local Markdown links/anchors resolved; role, SQL/S3/container/admission/limit/publication rules and analytical schemas preserved; `git diff --check` clean. No external OpenAPI validator is installed, so validation was limited to structure, references and semantic comparisons. These checks concern the design and patch only. No application runtime, login, seed, password hash, migration or permission test ran; main contains documentation and OpenAPI, not a runnable auth implementation.

## Remaining work and next action

Implement auth migrations, the seed command, password verification and bounded login throttling; pin/lock the hashing library and verify the full local persona/session flows. These are implementation gates, not missing author decisions for this documentation patch.

[ME] Review the branch diff before implementing the local authentication slice. No merge or pull request is part of this task.
