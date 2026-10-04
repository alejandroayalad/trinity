# SQL isolation and HTTP delivery commits

Date: 2026-10-04. Decision references: A9, A16, A19, A20.

## Authority and scope

[ME] Alayala requested commits for isolated execution, HTTP delivery and any remaining validator/DataFusion work. This extends the earlier autonomous T05–T20 authorization. No push, PR, retained database migration or live publication was requested.

[YOU] Reviewed and separated SQL changes from concurrent catalog and preview work. The existing validator/DataFusion implementation is `e851e28`; the remaining qualified-column alias correction is `1e3c072`. Kept the paired single-statement commits intact. Prepared isolated snapshots from the Git index so uncommitted catalog routes cannot hide missing dependencies.

## Isolation implementation and evidence

Validated SQL and one pinned publication enter the supervisor. PostgreSQL reserves shared capacity; verified files enter a generated request directory. A fixed-image, network-disabled container reads only that directory. The supervisor validates the complete result, confirms termination/removal and only then releases capacity. An ambiguous Docker create retains capacity; expiry alone does not release it.

Includes admission migration, publication pinning, GET-only staging, response models, service admission, Docker management/framing, runtime entrypoint, supervision and recovery. These are required dependencies of isolation. The auth test reset includes the new foreign-key tables without committing the separate catalog fixture refactor.

Checks on the isolated staged snapshot:

- SQL suite: 58 discovered, 53 passed, five real-container tests skipped before opting in (1.395 seconds).
- Built `backend/Dockerfile.query` from that snapshot with the locked environment.
- Opt-in Docker suite: all seven checks passed (5.252 seconds), including real execution, read-only mount/sibling/network/credential denial probes, kernel OOM, timeout removal, wrong-owner rejection and bounded frame handling. Probe tests use fixed test-only Python commands; the normal execution test uses the production runtime.
- Engine regression before commit: all ten checks passed (0.495 seconds), including canonical qualifiers with a table alias.

## Boundaries

Synthetic manifests and local Parquet bytes are used. No live EIA/S3 permission proof, retained-account query, frontend hiding or retained migration is claimed. Real recovery acceptance abandons a running reservation; it does not yet prove an actual API-process SIGKILL or every late-create/start race. This commit records implemented behavior and measured checks, not completion of every T16/T18 acceptance scenario.

HTTP delivery and final regression evidence will be added below after verification. Maintain data evidence — ongoing. Next: [YOU] verify the exact HTTP delivery snapshot and preserve unrelated work.
