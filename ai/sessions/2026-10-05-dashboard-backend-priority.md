# Dashboard backend priority and proposal

## Objective and contributions

[ME] Alayala selected dashboard backend planning first, followed by schedule settings, Plant filter and failed-run recovery. No code or Git delivery was requested.

[YOU] Codex inspected branch `frontend` at `444795f`, status, README, CONTRIBUTING, PRODUCT, AGENTS, relevant decisions/contracts, FINDINGS metric evidence, frontend drafts and backend routes. It traced catalog/preview publication and execution flow, read the external handoff README and dashboard logic, and viewed the retained Analyst dashboard screenshot. It drafted the [dashboard proposal](../../sdd/national-dashboard/proposal.md).

Concurrent frontend changes appeared during inspection: DECISIONS, the frontend proposal/specification, its session and a copied design-reference directory. These were reread where relevant and left untouched. No frontend technology/token-storage decision was replaced. Design attribution follows [A25 and the handoff record on the inspected frontend commit](https://github.com/alejandroayalad/trinity/blob/444795f0156983255b7756e175ab4cf5cdca8438/ai/sessions/2026-10-04-figma-brand-handoff.md); this task makes no new claim about the HTML package's author.

## Decisions and corrections

A9/A16/A19 retain authority over metric semantics, API shapes, permissions and isolated execution. Two missing national handlers are sufficient for the national screen. Existing facility preview supplies Analyst/Admin contributions and sparklines, subject to runtime activation and complete pagination.

The handoff's latest cards differ from A16's range-end summary and frontend draft R24. The proposal recommends separate latest/range requests without changing the API. This is a recommendation, not an accepted decision. Frontend D03's eight-day sparkline and the retained screenshot's 30-day label also differ; either fits existing preview. Duration can remain a frontend choice without blocking backend scope.

The original frontend delivery order is superseded for backend planning by alayala's current priority. Its concurrently edited file was preserved; the new proposal records precedence. Mock values were not used as EIA evidence. Maintain data evidence — ongoing.

## Checks and boundaries

Static evidence: route-decorator search under `backend/src/trinity/`, `main.py:create_app`, `PreviewService.prepare`, `execute_preview`, `get_catalog` and `preview_execution_factory`. Dashboard/metric handlers are absent; preview defaults off. No running deployment state was inferred from historical operator notes.

Validation passed: all 10 local links in the proposal/session resolve; both documents have balanced code fences and no trailing whitespace; both planned GET operations exist in OpenAPI; `git diff --check` passed. The NOTES diff and new document content were reviewed for scope and consistency. No backend tests were run because no application code changed. No builds, migrations, API calls, EIA/S3 operations, dependencies, commits or remote writes were performed. An initial documentation patch failed its NOTES context match and applied no changes; the corrected patch created this session and the proposal and added a NOTES contribution.

Done: two-route scope, screen/data mapping, reuse boundaries and verification plan.
Pending: proposal review, then dashboard specification.
Blocker: none for planning; retained runtime/publication readiness is unverified.

Next action: [ME] Review the latest-card recommendation in the proposal.

## Subsequent branch delivery authorization

[ME] Alayala requested `pending-endpoints-frontend` from `main`, cherry-picking this work, followed by Schedule settings, Plant filter and failed-run recovery in separate commits and a push. [YOU] verified `main` and refreshed `origin/main` both resolve to `eed2ab6`. The dashboard proposal, this session and its NOTES contribution form the focused source commit. Design references use the inspected frontend commit so the endpoint branch does not require unrelated frontend files. This Git authorization supersedes the earlier no-delivery boundary; the planning-versus-implementation scope for subsequent slices is being clarified separately.

## Card date resolved on `feat/national-dashboard`

[ME] Alayala requested one branch per proposal from `pending-endpoints-frontend` (`8746bb8`) and pushed `feat/national-dashboard` as the working branch. He then rejected the latest-card recommendation and selected range-end cards: for Jan 1–31, the cards show January 31 with the label “Range end: Jan 31.” He cited the A16 contract as the reason.

[YOU] Verified that `docs/api-contract.md` defines `summary` as the requested range's end date, equal to the last day point. The choice needs no API change and no new decision entry; it applies A16. Updated the proposal's card section. Documentation only; no tests were run because no code changed.

Next action: [ME] Approve writing the dashboard specification.
