# Dataset preview design and tasks — October 4, 2026

## Objective and authority

[ME] Alayala confirmed specification D01–D03, then said “continue” in response to the request to draft design/tasks. This authorizes those planning artifacts only. The active SQL terminal remains a separate workstream.

[YOU] AI inspected current repository status, CONTRIBUTING, the approved preview specification, A9 diagnostic/publication rules, A15 query responsibilities, current SQL service/router/configuration, shared admission migration/repository, staging, supervision, runtime contracts/entrypoint/engine and the database runner. Inspected HEAD was `e851e28` on `feat/catalog-permissions`; shared implementation files were changing concurrently. No SQL implementation or test was modified or executed by this turn.

## Design result

The [design](../../sdd/dataset-preview/design.md) specifies one preview path through the shared isolated runtime, with strict query-pair parsing, a separately authenticated cursor, typed DataFusion expressions, full-key lookahead pagination and exact bounded response assembly. The [tasks](../../sdd/dataset-preview/tasks.md) separate ongoing evidence from four future stages: pure request/cursor/response components, shared execution/endpoint integration, real database/HTTP/container acceptance, then retained-account operator handoff.

Design mechanics use standard-library HMAC-SHA-256 with a bounded canonical payload and configured signing/verification keys; no new production package is proposed. Keys stay in trusted API configuration, never the query container, source control or logs. Restart/rotation behavior preserves the approved absence of time-only cursor expiry. Actual key provisioning remains future private operator work.

The typed preview operation must extend shared runtime envelopes and result dispatch in coordination with SQL, preserving SQL policy revalidation and public behavior. A matched producer/runtime protocol and image are required; incompatible messages fail closed. Current shared lifecycle files exist, but this planning inspection is not proof they pass runtime acceptance.

## Concrete dependency discovered

Current QueryResponse permits only empty diagnostics. The inspected publication pin carries public metadata/manifest identity, but not the complete frozen diagnostic projection required by preview. The three inspected migrations do not create A9 validation_results. Therefore the design requires the canonical complete producer/read model before delivery; absence cannot be represented by diagnostics=[]. Reinspect after concurrent work, reuse authoritative persistence where supplied, and coordinate any missing migration/producer prerequisite rather than silently implementing refresh/publication or activating a candidate.

Input → flow → output: current session plus typed filters/cursor → one publication and committed shared rate/capacity → selected verified files and typed isolated operation → validated complete-key page and authenticated continuation → confirmed cleanup. Failure example: a copied facility cursor gives Viewer the safe 404 before file access; a timeout retains its reservation until actual termination is known.

## Verification and limits

Document checks passed: `git diff --check`; 32 local links/anchors and balanced fences across five preview artifacts; all S01–S31 mapped to stages and all 24 specification requirements preserved; task checkboxes show no implementation as completed. A worst-case synthetic cursor calculation using maximum four-byte source-ID characters produced 2292 payload bytes and 3137 total token characters, within the designed 3000/4096 bounds. Focused review checked D01–D03 preservation, shared-interface changes, provenance fail-closed behavior, scope and evidence gates. No preview implementation, backend test, DataFusion query, HTTP/database call, Docker build/container launch, migration, secret generation or cloud action ran in this planning turn. Cursor-size calculation uses synthetic public strings only and is not cryptographic/runtime acceptance.

Only new preview design/tasks, existing preview status/index entries, NOTES and supporting sessions were edited. No canonical role, wire field, accepted D01–D03 rule or dependency version changed. No commit, push or PR. Maintain data evidence — ongoing; no new source observation or finding.

## Checkpoint

Done: preview design/tasks drafted, shared interface boundaries and provenance dependency explicit.
Pending: implementation authorization and all three preview evidence categories.
Blocker: no planning blocker; shared-runtime acceptance and complete frozen provenance are prerequisites to endpoint delivery.
Next: [ME] authorize Step 2 or select the bounded implementation scope.
