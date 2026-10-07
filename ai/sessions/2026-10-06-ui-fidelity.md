# Session - UI fidelity to the Figma handoff

Date: 2026-10-06. Mode: implementation. Branch: `ui/handoff-fidelity` from `origin/main` `bf52757`.

## Objective and contributions

- [ME] Alayala reported that the running frontend did not match his Figma mockups (dashboard, catalog, SQL Explorer, refresh list, run review, schedule). He asked for an SDD change (proposal, spec, design, tasks) drafted in parallel by agents, then implementation. He waived per-screen approval for matching the handoff screenshots. He accepted that states without a design reuse prototype patterns, with screenshots shown to him.
- [YOU] OpenCode traced the cause, drafted the shared brief, ran four parallel drafting agents (the task tool offered no model choice, so Sonnet could not be selected), reconciled the documents and implemented V0–V9.
- Design attribution follows [NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026) and A25: alayala's Figma mockups and the ChatGPT brand reference. This session applied that design; it did not author it.

## Cause (confirmed from code and captures)

`tokens.css` already matched the prototype. A 49-line global `app.css` used a different layout (white sidebar, gray main, a card per block, orange chart and meter) and global `label`/`input`/`table` rules that broke controls. Built components (Segmented, Tabs, Switch, Field, Tag) were unused, dates showed as ISO text and refresh screens printed raw codes.

## Changes

- SDD: [proposal](../../sdd/ui-fidelity/proposal.md), [spec](../../sdd/ui-fidelity/spec.md), [design](../../sdd/ui-fidelity/design.md), [tasks](../../sdd/ui-fidelity/tasks.md), [acceptance](../../sdd/ui-fidelity/acceptance.md).
- `app.css` deleted. The shell and each page use their own CSS Module and tokens only.
- New: `BrandLockup`, `PageHeader`, `ListTable`, `StepTimeline`, `shell/Sidebar.tsx`, `shell/ContextBar.tsx`, `lib/copy.ts`, `formatLocalTime`, `xTickIndexes`.
- Synthetic capture suite `frontend/tests/e2e/fidelity.*` for every handoff screen at 1440px and 924px, three state captures and a 320px overflow assertion.
- No backend, API, permission, dependency or lockfile change. Queries, retries and polling are unchanged.

## Checks

The commands and results are in [acceptance.md](../../sdd/ui-fidelity/acceptance.md#v1v10-result--2026-10-06). Summary: typecheck, lint, 136 unit tests, build and four Playwright configs passed under Node 26.3.0. The approved Node 24.21.0 build was not available. `session.spec.ts` and `data.spec.ts` were updated but not run.

## Open

- alayala's review of the captures, especially the `X-*` states.
- Commits; none were made.
- Maintain data evidence — ongoing. No EIA request was made; fixture values are design examples.

Next action: [ME] open `frontend/test-results/ui-fidelity-v10-fidelity/` and compare the captures with `docs/design-reference/2026-10-04-explorer-handoff/screenshots/`.
