# Root README rewrite from public repository examples

Date: October 6, 2026. Mode: documentation implementation and review.

## Objective and contributions

- [ME] Alayala requested a substantially better README and asked the agent to look at public repositories.
- [YOU] OpenCode inspected the root and component guides, accepted decisions, product/data contracts, current Compose files, relevant implementation, and the October 6 integration evidence. It read four public READMEs through GitHub's API and rewrote the root entry point.
- Existing frontend and `sdd/ui-fidelity/` changes were present at the start and belong to concurrent work. This task changes documentation only.
- Preserve the canonical [human Figma / ChatGPT brand attribution](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026) and the separate [Explorer package provenance](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md). No design adaptation or human understanding is inferred from this rewrite.

## Public references inspected

The references informed organization and presentation, not product claims or dependencies. GitHub's readme API returned each document; the commits below identify the latest README change returned during the review.

| Public README | Useful pattern applied to Trinity |
|---|---|
| [Metabase](https://github.com/metabase/metabase/blob/c78c9fed48b3793bcf2589106a8f77bb5acf3c75/README.md) | Lead with the user problem and capabilities; keep specialist documentation one link away. |
| [Evidence](https://github.com/evidence-dev/evidence/blob/505885dade016e8357f64fb10f0cf8e6e590dc55/README.md) | Short product explanation, recognizable brand, and a direct start path. |
| [Immich](https://github.com/immich-app/immich/blob/1c2bee9986db396da05cd655a20540e5e8701f91/README.md) | Visual identity, navigable sections, and clear feature/access information. |
| [SQLPad](https://github.com/sqlpad/sqlpad/blob/f792e1f6ad9f01be5a87f6c5af02aced45f04fed/README.md) | Concrete SQL-workspace description and links to runtime/developer instructions. Its README explicitly marks the project archived; it is only a presentation reference. |

No badges implying CI, coverage, licensing, a live demo, or completed visual acceptance were added. The optional dashboard image is explicitly a design reference with illustrative values, not a running-app screenshot.

## Corrections and implementation evidence

The previous root README accumulated historical delivery notices. For example, its October 6 opening reported completed frontend delivery and a live publication, while lower sections still said the explorer was unimplemented and frontend technology was open. The rewrite presents one reader-facing baseline and links the dated history instead of repeating those contradictory notices.

Relevant existing decisions: A4/A9/A14 (state, data, and storage), A16/A19/A20 (flow, permissions, and authentication), A17/A26 (toolchains), A24 (one-host publication recovery), A25 (authorship), and A27 (compressed evidence). No decision is added or changed.

### Source trace

- `compose.yaml` starts PostgreSQL and the API by default. Redis and background services require the `workers` profile. The query environment and Docker/staging mounts come from `compose.sql.yaml`.
- `auth.seed.seed_personas` in `backend/src/trinity/auth/seed.py` accepts 15–1024-character passwords for missing personas and preserves existing accounts. The CLI requires a terminal.
- `create_app` and `preview_enabled_from` in `backend/src/trinity/main.py` register the current feature routers and enable published preview/dashboard/choice reads only for the exact environment value `true`.
- `load_cursor_keys` in `backend/src/trinity/queries/cursors.py` requires an explicit key ring. It does not generate keys on startup. Refresh uses a separate key configuration.
- `frontend/vite.config.ts` binds the development server to loopback port 5173 and proxies `/api` to port 8000. Package scripts and engine requirements were checked in `frontend/package.json`; backend pins were checked in `backend/pyproject.toml`.
- `DATASETS` in `backend/src/trinity/contracts/datasets.py` supplies the table names, daily keys, string identifiers, and exact decimal fields used in the overview and SQL example.

The full-stack instructions explicitly require operator-supplied AWS storage/profiles, cursor keys, Docker socket access, a matching query image, migrations, and publication. The base startup is not described as a ready analytical dataset. Existing local credential/mount tradeoffs remain visible.

The Compose header already flags PostgreSQL 17.11 versus A17's 18.6. The README reports this unresolved difference rather than selecting or upgrading a version. Earlier component guides retain dated slice statements; the root directs readers to the October 6 integration record for the delivery baseline.

## Verification

| Check | Result |
|---|---|
| Relative Markdown/HTML links and heading fragments | 52 checked across the root README, this session, and the new Engineering Notes entry; all resolved. |
| Shell examples | All 10 fenced shell blocks passed `bash -n` or `zsh -n`, as applicable. Setup commands were parsed, not executed. |
| Document structure and npm scripts | Code fences and HTML details blocks balanced; documented `npm run` scripts exist in `frontend/package.json`. |
| Findings reproduction | `python3 scripts/generate_report.py --inputs evidence/findings/inputs --out <new temporary directory>` exited 0: `Historical claims reproduced: True`; 82,650 comparisons. |
| Reproduction identity | `cmp` confirmed generated `report.json` and `REPORT.md` exactly match `evidence/findings/expected-report.json` and `evidence/findings/REPORT.md`. |
| Diff review | Reviewed the root README and additive Notes diff; `git diff --check` passed. Existing frontend changes continued independently. |

The link/syntax checker was temporary tooling outside the repository. It checked only the new Notes entry rather than claiming an audit of all historical links. The findings command used the pre-approved temporary directory instead of overwriting an existing report.

An attempted SQL-policy smoke check could not use `backend/.venv/bin/python` because that environment is absent in this checkout. The available `python3` lacks `sqlglot`, so no runtime SQL validation is claimed. The example's table, columns, ordering, and limit were checked against `DATASETS` and the policy source. Dependencies were not installed for a documentation-only edit.

Application builds, full test suites, Compose startup, GitHub-rendered Mermaid, and a clean-checkout walkthrough were not rerun. The README's application test counts remain explicitly attributed to the earlier integration delivery record.

During the initial rewrite, no application service, dependency, image, database, EIA request, S3 object, commit, or remote state was changed. The backend environment example could not be read because the tool's file-access rules deny `.env.*`; configuration was checked against allowed source, Compose files, and existing guides instead. Private environment/credential files were not read.

## Git delivery authorization

[ME] Alayala subsequently requested: "okay commit and push". [YOU] Reviewed status, documentation changes, staged scope, recent commits, branch tracking, and the remote. The active branch is `ui/handoff-fidelity`; its inherited upstream initially points to `origin/main`. Delivery targets the same-named remote feature branch explicitly. One focused commit contains `README.md`, the additive `NOTES.md` entry, and this research/verification record. A concurrent UI-fidelity Notes entry appeared during staging, so the commit uses an isolated temporary index with only the README contribution. The separate UI changes and staged stylesheet deletion are preserved. The commit and remote history record the delivery outcome; this authorization does not request a PR or merge.

## Remaining work and next action

- Full clean-checkout setup remains a separate evaluator rehearsal, not a result of syntax/link checks.
- Visual/accessibility approval and complete browser acceptance remain open as recorded by the integration delivery.
- Maintain data evidence — ongoing. No findings or source values changed.
- Next action: [ME] Review the README opening and local setup path for clarity before the evaluator rehearsal.
