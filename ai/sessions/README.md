# Session index by theme

Start with the relevant theme, then follow its dated records. Filenames and paths stay unchanged so existing evidence links remain valid. Each session has one primary theme; cross-topic links inside the record preserve related decisions. Earlier statements describe their historical gate, not current authorization or delivery status.

The [catalog delivery guide](../../sdd/catalog-permissions/README.md) separates requirements, design, implementation and measured review evidence. The active continuation branch is `feat/catalog-permissions`: catalog and SQL are committed, and preview integration and Step 4 automated acceptance passed; Step 5 operator tooling is implemented, with delivery still disabled pending retained publication linkage and the operator run. The synchronized delivery branch is retained only as an equal reference. See the [reconciliation record](2026-10-04-catalog-sql-preview-reconciliation.md) for remaining implementation and runtime gates.

| Theme | Records |
|---|---:|
| [Catalog and permissions](#catalog-and-permissions) | 7 |
| [Authentication](#authentication) | 5 |
| [Data evidence and findings](#data-evidence-and-findings) | 5 |
| [Connector, Parquet and storage](#connector-parquet-and-storage) | 8 |
| [Architecture and contracts](#architecture-and-contracts) | 13 |
| [SQL implementation](#sql-implementation) | 9 |
| [Dataset previews](#dataset-previews) | 7 |
| [Delivery and working practices](#delivery-and-working-practices) | 7 |

## Catalog and permissions

- [2026-10-04 — Earlier catalog-inclusive Docker verification](2026-10-04-docker-catalog-initial-verification.md)
- [2026-10-04 — Catalog Docker operator check — October 4, 2026](2026-10-04-catalog-docker-operator-check.md)
- [2026-10-04 — Catalog and permissions — design and tasks](2026-10-04-catalog-permissions-design-tasks.md)
- [2026-10-04 — Catalog and permissions — implementation and evidence](2026-10-04-catalog-permissions-implementation.md)
- [2026-10-04 — Catalog and permissions — SDD proposal](2026-10-04-catalog-permissions-proposal.md)
- [2026-10-04 — Catalog and permissions — specification draft](2026-10-04-catalog-permissions-specification.md)
- [2026-10-04 — Catalog review and focused delivery](2026-10-04-catalog-review-and-delivery.md)

## Authentication

- [2026-10-02 — Session — Clerk and proposed application data models](2026-10-02-clerk-and-application-models.md)
- [2026-10-03 — Session — Seeded local authentication for the challenge](2026-10-03-seeded-local-authentication.md)
- [2026-10-04 — FastAPI and local login — implementation and delivery](2026-10-04-fastapi-local-auth-implementation.md)
- [2026-10-04 — FastAPI and local login — SDD drafting](2026-10-04-fastapi-local-auth-sdd.md)
- [2026-10-04 — Local login — reviewed slice closure and PR handoff](2026-10-04-local-login-review-close.md)

## Data evidence and findings

- [2026-10-02 — Session log — Capacity anomaly and facility comparison](2026-10-02-capacity-anomaly-facility-comparison.md)
- [2026-10-02 — Session log — Data findings and handoff](2026-10-02-data-findings-and-handoff.md)
- [2026-10-02 — Session log — Ongoing anomaly workflow](2026-10-02-ongoing-anomaly-workflow.md)
- [2026-10-02 — Session log — Palisades, pagination, and metadata](2026-10-02-palisades-pagination-and-metadata.md)
- [2026-10-04 — Phase 3 — Findings scripts and preserved inputs](2026-10-04-findings-scripts-reproduction.md)

## Connector, Parquet and storage

- [2026-10-03 — Session — First live EIA run](2026-10-03-first-live-eia-run.md)
- [2026-10-03 — Parquet preparation — SDD proposal](2026-10-03-parquet-preparation-sdd-proposal.md)
- [2026-10-03 — Parquet preparation — Step 1 schemas and exact parsing](2026-10-03-parquet-schemas-exact-parsing-step-1.md)
- [2026-10-03 — Python backend and EIA connector — continuous session](2026-10-03-python-backend-and-eia-connector.md)
- [2026-10-04 — Leading-decimal parser correction and live retry](2026-10-04-leading-decimal-parser-fix.md)
- [2026-10-04 — Live storage protection check — partial](2026-10-04-live-storage-protection-check.md)
- [2026-10-04 — October 1–2 preparation and independent S3 verification](2026-10-04-october-1-2-live-preparation.md)
- [2026-10-04 — Parquet preparation — Steps 2–5 and session close](2026-10-04-parquet-preparation-steps-2-5-close.md)

## Architecture and contracts

- [2026-10-04 — Next slice: Refresh and publication](2026-10-04-refresh-publication-next-slice.md)
- [2026-10-02 — Session log — A4: application state and outage queries](2026-10-02-a4-state-and-outage-queries.md)
- [2026-10-02 — Session — Data contract v1](2026-10-02-data-contract-v1.md)
- [2026-10-02 — Session log — Redis, BullMQ, and the outbox data contract](2026-10-02-redis-bullmq-outbox-data-contract.md)
- [2026-10-02 — Session log — Validation controls publication](2026-10-02-validation-publication-rule.md)
- [2026-10-03 — Session API security and dependency proposal](2026-10-03-api-security-dependency-proposal.md)
- [2026-10-03 — Session Approved API contract expanded](2026-10-03-approved-api-contract-expanded.md)
- [2026-10-03 — Session Backend contracts publication](2026-10-03-backend-contracts-publication.md)
- [2026-10-03 — Session — Backend stack review and proposed layout](2026-10-03-backend-stack-review-and-layout.md)
- [2026-10-03 — Session — Backend structure accepted](2026-10-03-backend-structure-accepted.md)
- [2026-10-03 — Session Dependency versions accepted](2026-10-03-dependency-versions-accepted.md)
- [2026-10-03 — Session — Python backend selection](2026-10-03-python-backend-selection.md)
- [2026-10-03 — Session Security contract and API split](2026-10-03-security-contract-and-api-split.md)

## SQL implementation

- [2026-10-03 — Session SQL scope by stage](2026-10-03-sql-scope-by-stage.md)
- [2026-10-04 — One-table read-only SQL — design and tasks](2026-10-04-single-table-sql-design-tasks.md)
- [2026-10-04 — One-table read-only SQL — proposal](2026-10-04-single-table-sql-proposal.md)
- [2026-10-04 — One-table read-only SQL — specification](2026-10-04-single-table-sql-specification.md)
- [2026-10-04 — SQL isolation and HTTP delivery commits](2026-10-04-sql-delivery-commits.md)
- [2026-10-04 — SQL implementation — validator through delivery](2026-10-04-sql-full-implementation.md)
- [2026-10-04 — SQL pair-programming gate — review preparation](2026-10-04-sql-pairing-review-preparation.md)
- [2026-10-04 — SQL pairing — whole-input single-statement check](2026-10-04-sql-single-statement-pairing.md)
- [2026-10-04 — SQL pairing — terminal semicolon and comments](2026-10-04-sql-terminal-comment-pairing.md)

## Dataset previews

- [2026-10-04 — Dataset preview Step 5: operator tooling and delivery handoff](2026-10-04-dataset-preview-step-5-handoff.md)

- [2026-10-04 — Dataset preview Step 4: automated acceptance passed](2026-10-04-dataset-preview-step-4-acceptance.md)
- [2026-10-04 — Dataset preview Step 3: shared execution and evidence reader](2026-10-04-dataset-preview-step-3.md)
- [2026-10-04 — Dataset preview Step 2: offline groundwork](2026-10-04-dataset-preview-step-2.md)

- [2026-10-04 — Dataset preview design and tasks — October 4, 2026](2026-10-04-dataset-preview-design-tasks.md)
- [2026-10-04 — Dataset preview SDD proposal — October 4, 2026](2026-10-04-dataset-preview-proposal.md)
- [2026-10-04 — Dataset preview specification — October 4, 2026](2026-10-04-dataset-preview-specification.md)

## Delivery and working practices

- [2026-10-04 — Catalog, SQL and preview task status correction](2026-10-04-slice-task-status-correction.md)
- [2026-10-02 — Session log — Document baseline](2026-10-02-document-baseline.md)
- [2026-10-02 — Session — Trinity repository import](2026-10-02-trinity-repository-import.md)
- [2026-10-03 — Session — Contributing and comment rules](2026-10-03-contributing-comment-rules.md)
- [2026-10-03 — Session — Vault reconciliation and handoff](2026-10-03-vault-reconciliation-and-handoff.md)
- [2026-10-04 — Catalog, SQL and preview branch reconciliation](2026-10-04-catalog-sql-preview-reconciliation.md)
- [2026-10-04 — Docker local setup — API and PostgreSQL](2026-10-04-docker-local-setup.md)
