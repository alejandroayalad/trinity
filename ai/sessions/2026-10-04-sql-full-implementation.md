# SQL implementation — validator through delivery

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`; initial HEAD `7d2e001`.
Status: implementation in progress; do not treat planned later gates as passed.

## Authority and contributions

[ME] Alayala first authorized autonomous T07–T12, then explicitly included T05–T06 without pairing, and finally authorized finishing T13–T20 including isolation and HTTP delivery. Incremental local commits remain authorized; no push or remote publication was requested. Earlier pairing stops are superseded for this work. Frontend UI remains a separate slice.

[YOU] Inspected the approved design/specification, current contracts, auth/publication/storage code, test/migration patterns and dirty worktree. Saved hashes for preserving concurrent catalog/Docker edits. Added the closed grammar, deterministic normalization and policy messages, bounded subprocess supervisor, restricted DataFusion entrypoint and real-Parquet tests. No credentials were read or printed.

## T05–T08 evidence

Input → full token/AST/argument checks → canonical names, output mapping and quoted operation → internal round-trip validation → independently restricted DataFusion over one synthetic local table → bounded exact result fragment. No production download or route uses this path yet.

`backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql*.py' -v`: 39 tests passed in 1.931 seconds. Includes the 25 allowed and 52 rejected review fixtures, real subprocess parsing/rejection/timeout recovery, real DataFusion execution of every allowed fixture, null ordering, duplicate labels/units, 1,005-row aggregate versus 1,000-row output cap, user LIMIT, byte budget, division-by-zero and decimal overflow rejection. This is not container isolation or HTTP evidence.

Observed correction: SQLGlot's PostgreSQL ROUND generator inserts CAST around an inferred floating AVG. A narrow generator override emits the already validated ROUND operands unchanged. Explicit ASC/DESC and NULLS FIRST/LAST are also emitted instead of relying on dialect defaults. The full policy rejects unapproved casts, spellings, argument fields and table references before execution; runtime recomputes the policy message.

Numeric evidence on decimal(24,6): direct values retain six places; AVG and division by integer produced ten fractional places; SUM retained six. ROUND(1.25,1)=1.3 and ROUND(-1.25,1)=-1.3. Every integer ROUND scale from -18 through 18 was executed; this measured range is enforced. Positive scales above source scale preserve available digits. Large squared source values fail instead of producing a float. Integer-only division follows integer SQL semantics (1/2=0). Empty aggregate output is COUNT=0, SUM/AVG=null. Public numbers remain strings without float conversion. These rules will be added to current design evidence before delivery.

The policy worker clears the inherited environment, closes inherited file descriptors, limits SQL bytes/tokens/nodes/depth, admits two workers per API process without a queue, and kills/reaps timed-out workers. The engine uses a 768 MiB pool with spill disabled; only a later verified container provides the 1 GiB process ceiling.

## Remaining gates

T09–T12 shared state/storage, T13–T16 container lifecycle and T17–T20 HTTP/operator acceptance remain in progress. No live EIA/S3, retained-database migration or frontend evidence is claimed. Maintain data evidence — ongoing.
