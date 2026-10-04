# Catalog and permissions

`GET /api/v1/catalog` returns national-only metadata to Viewer and all three dataset definitions to Analyst/Admin. Metadata is available before publication. Published readiness and newest-refresh status remain separate.

## Reading order

1. [Proposal](proposal.md): purpose, scope and the Viewer dashboard boundary.
2. [Specification](spec.md): R01–R15 requirements and S01–S24 acceptance scenarios.
3. [Design](design.md): permission checks, canonical definitions and one database snapshot.
4. [Tasks](tasks.md): implementation evidence and remaining human/frontend checks.
5. [Review and delivery](../../ai/sessions/2026-10-04-catalog-review-and-delivery.md): inspected behavior, current checks and publication scope.

The [implementation record](../../ai/sessions/2026-10-04-catalog-permissions-implementation.md) and [retained-account operator record](../../ai/sessions/2026-10-04-catalog-docker-operator-check.md) distinguish automated synthetic evidence from the earlier Docker operator check. Find related history in the [session index by theme](../../ai/sessions/README.md). Runtime commands are in the [backend guide](../../backend/README.md#catalog-metadata-and-operator-check).

This delivery contains the catalog SDD, backend implementation, tests and handoff. The reconciled branch also retains [SQL implementation](../../backend/SQL.md) and [preview planning](../dataset-preview/tasks.md); these are separate feature scopes. Viewer retains national metadata API access; hiding Catalog/SQL controls and denying direct frontend navigation remain pending in the frontend slice.
