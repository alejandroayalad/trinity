# Catalog Docker operator check — October 4, 2026

## Objective and authorization

Verify retained Viewer, Analyst and Admin accounts in the running local Docker database, provision only missing personas using private password prompts, and run the existing catalog operator check. Alayala explicitly approved the two existing migrations after inspection found no application tables. Decisions: A20/A21 local authentication and A16/A19 catalog permissions. This is operator evidence, separate from the [offline and automated database/HTTP results](2026-10-04-catalog-permissions-implementation.md).

## Contributions and execution

- [ME] Alayala authorized schema initialization and account provisioning, entered all passwords privately in macOS Terminal, and entered the saved passwords again for verification.
- [YOU] AI inspected the existing seed/check commands and Docker database, ran the approved migrations, launched the existing commands in an interactive terminal, and checked safe exit status and database summaries. No password, password hash or session token was printed, copied to chat or written to the operator status file.
- `docker exec trinity-api-1 /usr/local/bin/docker-entrypoint.sh alembic upgrade head` succeeded. `alembic current` returned `0002_app_entry (head)`. The explicit entrypoint loads the mounted database secret for libpq without displaying it.
- A read-only lookup confirmed all three personas were absent. `docker exec -it trinity-api-1 /usr/local/bin/docker-entrypoint.sh python -m trinity.auth.seed` created them through the existing hidden-input prompts. No reset command ran and no existing user was changed.
- `docker exec -it trinity-api-1 python -m trinity.auth.check --catalog` completed with exit 0. A temporary terminal launcher recorded only stage and exit code. The checker performs login, identity, settings authorization, role-filtered catalog validation, logout and post-logout denial for each persona.

The Docker binary was used through `/Applications/Docker.app/Contents/Resources/bin/docker` because it was not in the agent PATH. No container rebuild, restart, migration downgrade or volume deletion occurred.

## Corrections during the operator check

The first seed attempt failed after the Viewer password prompt. Read-only verification found zero users; database access and synthetic password hashing worked. Alayala confirmed the password was shorter than the required 15 characters. Retrying with valid-length passwords created all three accounts.

The first catalog check failed before any session was created. Alayala corrected his initial reply and confirmed he entered a different password at the check prompt. The check was rerun with the saved provisioning passwords; it then passed. No password was reset. A single nonexistent-user diagnostic login returned 401; it did not create a user or session.

## Observed results

| Persona | Stored role / active | Catalog permission verified | Sessions after successful check |
|---|---|---|---|
| viewer | viewer / true | national_outages only | 1, revoked |
| analyst | analyst / true | national_outages, facility_outages, generator_outages | 1, revoked |
| admin | admin / true | national_outages, facility_outages, generator_outages | 1, revoked |

The safe post-check database query confirmed every created session was revoked. `active_publication` had no selected publication. Thus this retained-account run proves the no-publication metadata path; publication-state coverage remains separate automated evidence. The API catalog route existed and rejected an unauthenticated request with 401.

## Limits and next action

No live data was published. This run does not prove preview rows, SQL execution/isolation, frontend navigation, timeout cleanup or live EIA/S3 behavior. No production code changed. No commit, push or PR was performed. Alayala's explanation of how a failed latest refresh can coexist with an active publication remains unobserved.

Done: both migrations, three retained active personas, and the interactive catalog check.
Pending: the separate behavior review and later frontend/query slices.
Blocker: none for this operator check.
Next: [ME] Review the active-publication versus latest-refresh distinction when continuing the catalog handoff.
