# Failed-run recovery specification delivery

Date: 2026-10-05

## Objective and authority

[ME] Alayala selected failed-run recovery as the next slice after ongoing settings work and requested the proposal/specification on the target branch with a push. [YOU] used the clean existing `pending-endpoints-frontend` worktree. A fetch confirmed zero commits of local/remote divergence before edits. No endpoint implementation, design, live recovery or merge is included.

## Contributions and evidence

[YOU] traced Refresh start/admission, disabled recovery action projections, Publication command replay and stopped-failure checks against A16/A19/A20/A23/A24 and the canonical API/OpenAPI. Updated the existing [proposal](../../sdd/failed-run-recovery/proposal.md) priority/status and drafted the [specification](../../sdd/failed-run-recovery/spec.md) with Human/LLM sections, R01–R12 and S01–S12. The earlier Plant-before-recovery ordering is superseded by the user's current selection.

P01 recommends current committed settings for the new run but remains unaccepted; no new accepted decision was added. Lock ordering, abandonment mapping and migration checks remain design work. Maintain data evidence — ongoing; no EIA values were fetched or changed.

## Checks and boundary

Both proposed methods/paths match canonical OpenAPI. Proposal/specification local link destinations, balanced fences, trailing whitespace and unique requirement/scenario IDs passed. The final four-file scoped diff was reviewed; `git diff --check` and `git diff --cached --check` passed. Backend tests were not run because executable files did not change. No runtime correctness is claimed.

The initial local write command could not start because `python` was unavailable; rerunning with `python3` wrote the documents. No partial first write occurred.

Done: proposal update and specification draft. Pending: specification review, P01 and design. Blocker: none for authorized Git delivery.

Next: [ME] review P01's recommendation to snapshot current settings for rerun. Final delivery identity is in Git history and remote refs.

## Subsequent acceptance

[ME] Accepted P01 and requested committing/pushing that acceptance, followed by design/tasks. [YOU] recorded the current-settings snapshot choice as an A16 refinement and marked the specification accepted for design. This supersedes the earlier pending-P01 status; implementation and runtime actions remain outside this authorization.
