# Pending frontend endpoints: isolated proposal delivery

## Authority and branch

[ME] Alayala requested `pending-endpoints-frontend` from `main`, cherry-picking the dashboard work, then separate commits for Schedule settings, Plant filter and failed-run recovery, followed by a push. He explicitly clarified “Planning proposals only.” No endpoint implementation, dependency installation, live activation, PR or merge is authorized by this request.

[YOU] Codex refreshed `origin/main` and verified both local and remote main at `eed2ab6`. It committed only the dashboard proposal, its session and its NOTES contribution as source `11b91bf`, then created sibling worktree `trinity-pending-endpoints-frontend` and cherry-picked with provenance as `594e4d4`. Concurrent frontend decisions/specification/assets remain in their original checkout. No unrelated frontend history is included in this branch.

## Schedule settings proposal

[YOU] Traced `settings.router.settings`, `get_settings`, `read_settings`, `RefreshService.start` and `refresh.repository.accept_run`, and checked A16/OpenAPI. Drafted the [schedule proposal](../../sdd/schedule-settings/proposal.md). Settings writes and status need new routes; actual scheduled admission also needs an explicit trigger path because current run acceptance records manual runs. The proposed scope includes scheduler integration without selecting its ownership/deduplication implementation prematurely.

[ME] Supplied priority and planning-only boundary. [YOU] Authored the proposal from existing accepted rules; it is not an accepted specification or runtime proof. Maintain data evidence — ongoing; no new outage observation was fetched or inferred.

Checks: source/contract tracing and document links/whitespace before each commit. No backend tests were needed because these commits change documentation only. Final verification results follow after all proposals are complete.

Done: isolated branch, dashboard cherry-pick and Schedule settings proposal.
Pending: Plant filter and failed-run recovery proposals, final checks and push.
Blocker: none.
