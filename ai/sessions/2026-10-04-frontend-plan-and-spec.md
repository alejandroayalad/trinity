# Frontend delivery plan and specification

## Objective

Plan delivery of the Trinity web pages from the design handoff package, then specify them. Alayala requested the plan first and development later.

## Human and AI contributions

[ME] Alayala requested the `frontend` branch, supplied the handoff package `design_handoff_trinity_explorer/` (in use since Saturday, per his statement), selected React + TypeScript + Vite (proposal Q1) and requested the specification.

[YOU] Claude created the local `frontend` branch from `main` (`eed2ab6`, equal to `origin/main`). The Figma/brand documentation was committed on this branch as `444795f` during this work; Claude did not make that commit. It read the handoff README, screenshots list and prototype file sizes, the API, data and security contracts and the backend routers. It drafted [the proposal](../../sdd/frontend/proposal.md) and [the specification](../../sdd/frontend/spec.md), and recorded A26. The author of `Trinity.dc.html` is not recorded (proposal Q2). Claude did not run the prototype in a browser.

## Decision references

- [A26](../../DECISIONS.md#a26--frontend-stack): React, TypeScript, Vite. Accepted.
- A25 keeps contract precedence over the mockup. Spec D01–D04 are proposals.

## Findings from the contract comparison

- Backend routes exist for auth, `GET /settings`, catalog, preview, SQL, refresh runs and candidates. Missing: national dashboard, offline-share metric, settings write, schedule status, facility/generator choices, rerun and resolve warning. Evidence: `@router.` search in `backend/src/trinity/`.
- The mock treats a missing observation as a null value in a row. The data contract has non-null `capacity` and `outage`; a missing observation is an absent row. Only dashboard `days` has null points.
- The mock uses `facility_name`, plant-name filters, `pub-`/`ver-`/`run-` labels, 1-decimal shares, a 200-row SQL cap, and "Latest day" / "Rows" columns. The contracts use `facility` + `facilityName`, UUIDs and `run_seq`, 2-decimal shares, a 1,000-row cap, and have no run-list end date or catalog row count.
- The mock's login error reveals whether an account exists. The API returns one generic `401`.

## Checks

Relative links in the proposal and specification resolve to existing files. The SQL D01 anchor exists. No code, test, build or browser check was run.

## Open questions

D01–D04 in the spec; proposal Q2 (HTML package author) and Q4 (copy the package into the repository).

## Next action

[ME] Confirm or change spec D01–D04.

## Update — October 5, 2026: Q1–Q4 answers

[ME] Alayala answered:
- Q1: approval covers React, TypeScript and Vite only. List every other dependency.
- Q2: keep the authorship of `Trinity.dc.html` and its README pending in A25. Do not attribute them to a tool without evidence. Design images and prompts were generated in a Codex chat.
- Q3: memory-only token. A reload requires a new sign-in. Bearer header only, never URL parameters. Clear it on sign-out or expiry.
- Q4: copy the package to `docs/design-reference/` without `support.js`, keep the originals and document provenance and exclusions.

[YOU] Claude applied these answers:
- Updated A25 (pending authorship note) and A26 (scope of approval and D01).
- Updated spec D01, R07, R11, S04 and the review gate, and added R05a and the [dependency list](../../sdd/frontend/spec.md#dependencies-pending-approval).
- Copied 24 files to [docs/design-reference/2026-10-04-explorer-handoff/](../../docs/design-reference/2026-10-04-explorer-handoff/PROVENANCE.md). Excluded `support.js` (SHA-256 recorded) and `.DS_Store`.
- The originals in the Downloads folder were not changed. Before copying, a scan of the HTML and README found only Google Fonts URLs and no secrets.

Checks: all 24 copies matched their originals by SHA-256. No code, dependency or browser check was run.

Later the same day, [ME] alayala accepted D02, D03 and D04 as proposed. The same message selected `sessionStorage` for D01, which conflicts with his earlier memory-only answer. [YOU] kept memory only in the documents until he chooses. That message also asked who created the package. Claude has no evidence of the author, so A25 keeps it pending. The message also made Q4 conditional on permission to include the assets; the copy is already made and awaits his confirmation of that permission.

[ME] Alayala then selected `sessionStorage` for D01, explained that the earlier text he pasted had a problem, and requested design and tasks. [YOU] Claude updated D01, R07, S04 and A26.

Next action: see the design and tasks update below.

## Update — October 5, 2026: design and tasks

[YOU] Claude drafted [design](../../sdd/frontend/design.md) and [tasks](../../sdd/frontend/tasks.md). It read current npm versions and peer ranges with `npm view` (read-only) and the Node LTS list from nodejs.org. Findings:
- `typescript-eslint` 8.71.0 accepts TypeScript `>=4.8.4 <6.1.0`, so the design proposes TypeScript 6.0.3 instead of the latest 7.0.2.
- `@testing-library/react` needs `@testing-library/dom` as a peer.
- Local Node is v26.3.0. Current LTS is v24.21.0. Vite 8.3.2 accepts `>=22.12.0`.

The spec's dependency list now also names `@types/react`, `@types/react-dom`, `@eslint/js`, `globals` and `@testing-library/dom`.

Checks: links resolve and `git diff --check` passes. No package was installed and no code was written.

Next action: [ME] approve or change the package versions in the design.

## Update — October 5, 2026: approval and implementation request

[ME] Alayala asked Claude to implement all ten frontend tasks from the design and tasks, with the proposed package versions, Node.js 24.21.0 and TypeScript 6.0.3, and to commit each slice. [YOU] Claude marked the design and tasks as approved for implementation and recorded the package approval in tasks step 1. Implementation work and its checks are recorded in the [implementation session](2026-10-05-frontend-implementation.md).
