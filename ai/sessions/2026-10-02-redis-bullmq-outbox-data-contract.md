# Session log — Redis, BullMQ, and the outbox data contract

Date: October 2, 2026. Timezone: America/Merida. Scope: data-model discussion and accepted-decision documentation. This is an AI-written summary, not a verbatim transcript.

## Objective and authorization

Continue the data-contract discussion and record alayala's selected background execution and queue design. Alayala explicitly requested that the accepted `job_outbox` choice be included in DECISIONS.md. This task authorizes documentation; it does not authorize application implementation.

## Contributions

- [ME] Alayala required a background worker for the full refresh pipeline and bounded concurrency. He selected PostgreSQL + Redis + BullMQ over the PostgreSQL-backed BullMQ option, accepted `job_outbox`, and requested the decision update.
- [YOU] AI read the current project documents, the local brief's US-08 requirement, and saved source metadata. AI consulted official BullMQ and outbox documentation, compared queue backends, explained the dispatch failure case, and drafted the accepted decision entries and supporting notes.

## Decision references

[A6](../../DECISIONS.md#a6--background-refresh-with-bullmq-and-redis-closed) is the canonical worker and queue decision. [A7](../../DECISIONS.md#a7--transactional-job_outbox-for-reliable-dispatch-closed) is the canonical dispatch decision. A2–A5 still govern refresh eligibility, validation, approval, and the PostgreSQL/Parquet/DataFusion responsibilities. The earlier open execution references now point to A6 and A7.

The earlier candidate entity lists and suggested field types are discussion drafts. This update does not accept a complete PostgreSQL schema, choose backend language or authentication, or set numeric concurrency limits. Other required data-contract choices remain open.

## Corrections

AI initially framed the concurrency discussion around extraction tasks. Alayala clarified that the background worker covers the entire refresh pipeline. AI recommended PostgreSQL-backed BullMQ to reduce services; alayala selected Redis. The final record follows his choice.

The outbox example describes a failure case to design and test, not an observed Trinity defect. Duplicate dispatch remains possible, and later loss of an acknowledged Redis job needs a separate recovery design. Safe retries do not establish exactly-once delivery or prove publication correctness.

## Checks and results

The documentation folder is not a Git repository, so a Git working-tree diff is unavailable. Changes are reviewed using a unified diff against exact pre-edit snapshots. Checks cover unique A1–A7 identities, decision-table/heading agreement, changed execution references, local links and anchors, balanced code fences, and preservation of prior content. The write step verifies that the originals still match the snapshots and that saved bytes match the reviewed drafts.

Official-source checks support the documented queue features and outbox pattern. No dependencies were installed; no implementation, database migration, EIA request, worker execution, queue integration test, or benchmark ran. No commit, push, or remote mutation was performed.

## Open questions and next action

The remaining details are listed in A6 and A7. Continue the data model without treating the queue library's internal state as the complete application model.

Next: define the refresh record and `job_outbox` fields, keys, and transaction boundary.
