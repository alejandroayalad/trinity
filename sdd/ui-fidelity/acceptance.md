# Acceptance record: UI fidelity (`ui-fidelity`)

Date started: 2026-10-06. [YOU] OpenCode keeps this record; [ME] alayala reviews it.
Design attribution: alayala's Figma mockups and the ChatGPT brand reference ([NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026), A25). Captures use synthetic data from `frontend/tests/e2e/fidelity-fixtures.ts`. Mock and fixture values are design examples, not EIA evidence.

Handoff folders: `H/` = `docs/design-reference/2026-10-04-explorer-handoff/screenshots/`; `R/` = `docs/design-reference/2026-10-04/`.
Captures: `frontend/test-results/ui-fidelity-<slice>/pages/` (not tracked by Git).

## V0 baseline — 2026-10-06

Toolchain: shell Node 26.3.0. The approved Node 24.21.0 build was not present in the temporary folder, so it was not used. Commands from `frontend/`, with `npx vite --host 127.0.0.1 --port 5173` running:

| Command | Result |
|---|---|
| `npm run typecheck` | Passed. |
| `npm test` | 128 passed in 12 files. |
| `npx playwright test --config tests/e2e/presentation.config.ts --output test-results/ui-fidelity-v0` | 3 passed. |
| `npx playwright test --config tests/e2e/fidelity.config.ts --output test-results/ui-fidelity-v0/pages` | 16 passed (captures only; no visual assertion). |

Main gap per screen, observed in the V0 captures against `H/`:

| Screen | Main gap | Class |
|---|---|---|
| Shell (all) | White sidebar and gray main are reversed; single wordmark image; "Overview"/"Schedule" labels; no Administration group, count pill or avatar; bar values have no labels, raw ISO date, plain "Ready" text, button "Awaiting review" | to fix (UF-S*) |
| 01 Sign-in | Plain card, "Sign in" heading instead of brand line, 130px wordmark, button not full width | to fix (UF-A*) |
| 02/04 Dashboard | Card per KPI, orange meter and line, separate orange range buttons, visible "Selected range loaded.", 2 ISO x labels, no tooltip, no header meta list | to fix (UF-D*) |
| 03 Contributions | Plain buttons and MW text; no bar list or detail column | to fix (UF-D17–D22) |
| 05 Daily values | Each date is a full button; ISO dates; no scroll box or tags | to fix (UF-D13–D14) |
| 06 Catalog | Table in a card with Description column; no row links with arrows | to fix (UF-C01–C03); Rows column stays omitted (R32) |
| 07–09 Table view | Mono h1, stacked search above select, filters and table in cards, 40px inputs | to fix (UF-C04–C08) |
| 10–11 SQL | Card editor, plain gutter, one example button, no Results header, schema as h3 + paragraphs, error title "✕ Error" | to fix (UF-Q*) |
| 12 Refresh runs | Raw `review_required` text, no subtitle or summary strip, table in a card | to fix (UF-R01–R03, UF-X10) |
| 13–14 Run review | No step timeline; raw `succeeded`, `not_started`, `share_out_of_range`; ID centered across the card; Approve not orange | to fix (UF-R04–R13, UF-X01–X02) |
| 15 Run failed | "Refresh failed" callout with 8-char ID text; timeline missing | to fix (UF-R15) |
| 16 Settings | Native checkbox distorted by global rules; card; "Save schedule" | to fix (UF-T*) |
| 17 Unavailable | Close match; orange "Go to Refresh" for Admin only | to fix (UF-A08) |

The 320px pass recorded its overflow list as a test annotation only; it does not assert in V0.

## V1–V10 result — 2026-10-06

[YOU] OpenCode implemented V1–V9 in one pass and ran the V10 commands below. Same toolchain and dev server as V0.

| Command (from `frontend/`) | Result |
|---|---|
| `npm run typecheck` | Passed. |
| `npm run lint` | Passed, zero warnings. |
| `npm test` | 136 passed in 13 files (128 before; 8 new: copy map, `formatLocalTime`, `xTickIndexes`, shell groups and count, run review without raw codes). |
| `npm run build` | Passed; `check-build.mjs` found no prototype controls, fixtures or test identities. |
| Playwright `presentation.config.ts` | 3 passed. |
| Playwright `explorer.config.ts` | 2 passed. |
| Playwright `session-reliability.config.ts` | 4 passed. |
| Playwright `fidelity.config.ts` | 19 passed, including the 320px no-overflow assertion on 7 pages. |
| `git diff --check` | Passed. |

Not run: `session.spec.ts` and `data.spec.ts` need the live local stack and seeded passwords. Their copy assertions were updated to the new text but not executed, so their axe checks also did not run.

Tests changed for copy or structure, not weakened:
- Old copy replaced with the spec copy: "Save schedule" → "Save", nav "Schedule" → "Settings", ISO headings → "D Mon YYYY", combined-share sentence, "Refresh failed" → "✕ Run failed", contribution heading.
- `presentation.test.tsx`: the chart viewBox is now 260px high, and the outlier hook is `data-part`.
- `presentation.spec.ts`: tick labels are HTML, fixed at 11px, and checked to stay inside the frame without overlap. The old check required 13px or more, because the SVG text used to scale; the handoff sets 11px labels that never scale.

### Differences that remain

| Screen | Difference from `H/` | Class |
|---|---|---|
| All | "Illustrative data" pill and prototype controls absent | Contract (R05) |
| All | IDs show 8 characters (`5c2e9a71`), not `pub-…`/`ver-…`; review pill names the run, not the candidate | Contract (R21; `/me` has the run only) |
| 02 | Hero shows 2 decimals (14.41%) | Contract (D04) |
| 02 | Range label "Last 365 days" | Contract (R23) |
| 03 | No facility is selected on load; the detail column asks the user to select one | Accepted: auto-selection would send an unrequested sparkline read and change tested request counts |
| 03 | Sparkline plots outage MW, not share | Contract difference recorded in spec |
| 06 | No Rows column; "Dataset" column shows `label` | Contract (R32) |
| 07–09 | Extra "Apply dates" button and "Search facilities" field; dates as "27 Sep 2026" | Contract (R34, explorer-state draft rule) |
| 10 | Default query and examples run real SQL; "NULL" chip without "not reported" | Contract (R40, D04) |
| 12 | Start refresh is disabled with a sentence while a run awaits review | Contract (A16 server action) |
| 13 | Run title "Run #1044"; Publish row carries the review state | Contract (R21, R50) |

### Undesigned states (UF-X12)

Captures: `frontend/test-results/ui-fidelity-v10-fidelity/fidelity-X-*/`, plus the 15 run-failed capture. They use error/warning callouts, the dashed box and badges only. alayala has not reviewed them yet.
