# Retained persona password rotation

Date: 2026-10-05
Branch: `feat/schedule-settings` (worktree `trinity-schedule-settings`); uncommitted.
Decision: A20 operator password rotation refinement in [DECISIONS.md](../../DECISIONS.md#a20--seeded-local-authentication-for-the-challenge-closed).

## Objective

Alayala no longer knows the retained persona passwords, so the S20 check of [schedule settings](../../sdd/schedule-settings/tasks.md) cannot run. Rotate them without resetting any other application state.

## Human and AI contributions

- [ME] Alayala stated the constraint: do not modify setup or refresh state; stop before the mutation. He approved the rotation design.
- [YOU] Claude (OpenCode) read `auth/seed.py`, A20 and `docs/security-contract.md`, proposed the design, wrote `auth/rotate.py`, `tests/test_auth_rotate.py` and the README paragraph, ran the checks below and took a read-only snapshot of the retained database.

## Why a new command

`seed_personas` skips any existing persona, by design: A20 and the security contract forbid a silent password reset and a recovery endpoint. The new command is explicit, terminal-only and limited to `local_users.password_hash`.

## Checks

| Check | Result |
|---|---|
| `tests/test_auth_rotate.py` on disposable PostgreSQL 17.11 | 7 passed (3 offline, 4 database). The database tests fill sessions (live and revoked), login limits, setup, a published version, a second run with its outbox row and receipt; then copy every public table. A rotation changes only the chosen hashes; the old password fails, the new one logs in, the unrotated persona and an existing session keep working. Short password, different entries, wrong role, inactive, missing persona, a role change while typing and a COMMIT failure leave every table identical. |
| Full offline suite | 630 ran, all passed, 207 skipped (opt-in) |
| `tests/run_local_auth_checks.py` | 112 passed |

`local_users` has had no schema change since migration `0001`, so the head-schema tests apply to the retained database at `0002_app_entry`. That is an inference from the migration files; the command has not run against the retained database.

## Retained read-only snapshot (before)

Taken 2026-10-05 18:29 UTC with `docker exec -i trinity-postgres-1 psql -X -q -U trinity -d trinity` in a `REPEATABLE READ READ ONLY` transaction. Each line is `table|rows|md5 of sorted rows`; `local_users` excludes `password_hash`. Per-persona hash digests were stored in a temporary file only, not here.

```text
active_publication|1|ec1659ec273727ff28db2af1e40f6dbb
alembic_version|1|e81185ece5c4e9c5e9dd8d98f1d9579a
approvals|0|d41d8cd98f00b204e9800998ecf8427e
auth_login_limits|3|5a01d3f90f0185aecddc622c93815afe
data_versions|0|d41d8cd98f00b204e9800998ecf8427e
failure_warnings|0|d41d8cd98f00b204e9800998ecf8427e
local_sessions|5|5c70c4966dcdedfda0b6cd1904bd498c
local_users|3|e806dbdaa91a3906b8054bebf9b36708
publication_events|0|d41d8cd98f00b204e9800998ecf8427e
refresh_control|1|9fa842a2ea3c675c83df5cb56bda6833
refresh_runs|0|d41d8cd98f00b204e9800998ecf8427e
refresh_steps|0|d41d8cd98f00b204e9800998ecf8427e
shared_settings|1|56884f1ee89ef52de7178c87df2f7139
```

Any login or app use between this snapshot and the rotation changes `local_sessions` or `auth_login_limits`; the after-snapshot must be taken before the login check.

## Retained result (after)

[ME] Alayala ran the rotation and then the S20 check (`--schedule`), which signs in all three personas. He did not paste the rotation output line. [YOU] Took the after-snapshot at about 18:40 UTC, after the S20 check, so it also contains the check's effects.

| Table | Before → after | Explanation |
|---|---|---|
| `local_users` (without `password_hash`) | identical | IDs, usernames, roles, status and creation times unchanged |
| Password hashes | admin, analyst, viewer: changed | All three rotated |
| `local_sessions` | 5 → 8 rows | The 5 earlier rows are identical (same digest `5c70c496…` for rows created before 18:29:16 UTC). 3 new rows from the check's sign-ins, all revoked by its logouts |
| `auth_login_limits` | 3 → 5 rows, new windows from 18:35 UTC | Login counters from the check's sign-ins. The retained data cannot separate this from the rotation; the disposable tests show that rotation does not touch this table |
| `shared_settings` | changed | S20 save: revision 1, enabled, `06:15`, `America/New_York` |
| All other tables, including `refresh_runs` (0), `refresh_control`, `active_publication`, `alembic_version` | identical | — |

Conclusion: no user ID, role, status, earlier session, run, slot, publication or migration state was reset. The only changes are the rotated hashes and the expected effects of the S20 check.
