# Presentation fixes — QA-07, QA-10, QA-11

## Scope and contributions

[ME] Alayala requested readable mobile chart labels, unique SQL header keys and
accurate candidate copy after the Explorer-state delivery. [YOU] Codex traced
current frontend code and A16/API candidate states, implemented the three fixes,
and verified them. The original QA report remains absent as documented in the
[Explorer-state session](2026-10-06-explorer-state-implementation.md); IDs and scope
come from the user's instruction. No new product decision was introduced.

Explorer-state commits `6c9e780` and `4ad15d0` were pushed to
`origin/integrate/frontend-main` before this slice. These presentation edits remain
uncommitted. Backend and concurrent documentation work were left intact.

## Root causes and results

### QA-07 — fixed in automated presentation checks

- Severity and scope: moderate frontend presentation, uncommitted.
- Expected: chart labels remain readable on narrow screens without overlap.
- Observed before: `NationalChart` used an 800-unit-wide SVG and 12-unit text.
  At a 222 px chart width, labels scaled down to about 3.3 px. A CSS minimum
  height did not prevent SVG text scaling.
- Evidence: `NationalChart` in `frontend/src/pages/dashboard/NationalChart.tsx`
  observes displayed width with ResizeObserver, then calculates plot coordinates,
  clipping and hit areas from that width. `frontend/src/styles/app.css` retains
  a 310 px chart height and 14 px text. Measurements remain exact decimal strings.
- Failure scenario: open Dashboard at 320 px viewport width. The original viewBox
  shrank labels; the current browser regression measures all labels at readable
  height, inside the chart bounds, with separated date labels. It also checks
  390/1440 px and keyboard pinning of a negative observation.
- Recommended correction: implemented responsive coordinates and a tick-label
  gutter; missing-data hatching and outlier markers remain present.
- Validation still required: [ME] human visual acceptance, real-device/touch and
  screen-reader acceptance. The browser check used reduced motion.

### QA-10 — fixed in unit and browser checks

- Severity and scope: minor frontend rendering defect, uncommitted.
- Expected: SQL may return duplicate column names without React key collisions.
- Observed before: `DataTable` in `frontend/src/pages/shared.tsx` keyed headers by
  `Column.name`, although the API preserves duplicate names and ordered row cells.
- Evidence: headers now use their ordered column position as identity, matching
  the existing cell order. The visible names, units and exact values are unchanged.
- Failure scenario: two result columns both named `value` formerly had identical
  keys. Unit and browser tests now render both headers/cells without console key
  warnings; the unit check also replaces the rows and verifies their order.
- Recommended correction: implemented positional header keys; no SQL/API change.
- Validation still required: none for the reproduced rendering defect. The SQL
  browser response was simulated; no retained query or SQL policy was exercised.

### QA-11 — fixed in unit and browser checks

- Severity and scope: moderate misleading frontend copy, uncommitted.
- Expected: copy describes the server candidate status and does not invent approval.
- Observed before: `CandidatePanel` in `frontend/src/pages/refresh/Refresh.tsx`
  always said publication awaited approval, even for warning-free/published data.
- Evidence: `candidateCopy` uses disposition, publication, validation and review
  states. Terminal outcomes take precedence; published does not imply currently
  active. Preparing, warning-free, review-required, approved, queued/publishing,
  failed, blocked, discarded and superseded cases have distinct descriptions.
- Failure scenario: `review_status=not_required`, `publication.status=published`
  formerly implied an outstanding approval. It now says the candidate published
  successfully. Eleven state cases pass; the browser confirms published copy,
  no Approve button and GET-only requests.
- Recommended correction: implemented state-specific text. Action eligibility,
  confirmation dialogs, publication policy and mutation handling are unchanged.
- Validation still required: [ME] wording acceptance. Synthetic browser responses
  do not prove retained candidate or publication runtime behavior.

## Checks and artifacts

- `npm run typecheck`: passed from `frontend/`.
- `npm run lint`: passed with zero warnings.
- `npm test`: 113 passed across 12 files.
- `npx playwright test --config tests/e2e/presentation.config.ts`: three passed.
- `git diff --check`: passed; final implementation diff reviewed.
- Chart screenshots at 320 and 1440 px were visually inspected. Labels are readable
  and separate; the 390 px screenshot was generated and its geometry asserted.
- New browser artifacts are isolated under
  `frontend/test-results/presentation-2026-10-06/`, including `results.json`,
  `chart-320.png`, `chart-390.png`, `chart-1440.png` and published-candidate screenshot
  in their test subdirectories. Prior Explorer/live-QA artifacts were preserved.
- Initial focused verification caught one incorrect test geometry expectation and
  a fixture's widened unit type. Both were corrected before the passing full run.
- No dependencies, builds, backend edits, retained mutations, or credentials were
  introduced. Build and evaluator acceptance remain [ME] under AGENTS.md.

## Next action

[ME] Open Dashboard at a 390 px viewport and review the chart labels. Automated
checks are complete; human visual acceptance is not claimed.

## Delivery authorization

[ME] Subsequently authorized commit and push before starting logout/startup work.
[YOU] Kept implementation/tests and evidence in separate commits; excluded unrelated
backend and documentation changes. Build and human acceptance remain open.
