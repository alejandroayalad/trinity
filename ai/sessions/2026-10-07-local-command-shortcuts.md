# Local command shortcuts — October 7, 2026

## Objective and contributions

[ME] Alayala requested reusable local run commands after adding the hosted demo
link. [YOU] Codex traced README, Compose, the API secret-loading entrypoint,
frontend npm scripts and Vite configuration, then added Make targets and updated
the README. The existing demo-link edit is preserved. A19 local Compose and A20
local personas remain unchanged; no new architecture or production dependency.

## Flow and failure behavior

Operator configuration supplies private values to existing Compose services.
Explicit build, startup, migration and seed targets prepare the base API; the
frontend targets install locked dependencies and run Vite with its local API
proxy. Real-data startup layers compose.sql.yaml and the workers profile over
the same base project. Missing required full-stack values fail quiet Compose
validation before startup. Full startup can execute an enabled saved schedule.
Neither startup target runs migrations or seeds accounts automatically.

Stop targets call Compose down without volume removal; Vite stops separately
with Ctrl+C. Operators must use the same base/full mode across restarts and stops.

## Checks and results

- `make help`: passed; shows the commands and their effects without running them.
- `make -n` for all 14 operational targets: passed; reviewed emitted commands
  against Compose services, entrypoint and package.json.
- All README Make target references resolve; all shell examples passed shell
  syntax checks using bash or zsh as labeled.
- `git diff --check`: passed; scoped diff reviewed.

These are static and dry-run checks. No Docker build/start/stop, database
migration, account provisioning, npm installation, EIA/S3 operation, commit or
push was performed. Existing runtime acceptance does not establish fresh setup
with these wrappers. No application source changed or application tests reran.

## Checkpoint

Done: local commands, README usage and static verification.
Pending: [ME] clean-checkout setup rehearsal with private configuration.
Blocker: none for the command/documentation change.
Next: [ME] Run `make help` from the repository root to review the entry points.
