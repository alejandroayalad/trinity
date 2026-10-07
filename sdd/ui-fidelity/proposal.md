# Proposal: Trinity frontend visual fidelity (`ui-fidelity`)

Date: 2026-10-06
Status: Requested by alayala on 2026-10-06. He waived per-screen approval for matching the handoff screenshots. He approved the use of prototype patterns for states that have no design, with screenshots shown to him. Implementation is authorized for frontend presentation only.
Inspected branch/HEAD: `ui/handoff-fidelity`, created from `origin/main` at `bf52757`.
Basis: [sdd/frontend/proposal.md](../frontend/proposal.md) and [spec](../frontend/spec.md) (R03, R04, R13, R14, R20–R29, R32, R39, R62, R63, S25 stay valid); A9, A16, A19, A20, A25 in [DECISIONS.md](../../DECISIONS.md); [handoff README](../../docs/design-reference/2026-10-04-explorer-handoff/README.md), `Trinity.dc.html` and screenshots; [docs/design-reference/2026-10-04/](../../docs/design-reference/2026-10-04/).
Companion documents: [spec.md](spec.md), [design.md](design.md), [tasks.md](tasks.md).

## Human

### Goal

Make the running frontend look like alayala's handoff screenshots: Dashboard, Catalog, SQL Explorer, Refresh list, Run detail and Settings. Change presentation and copy only. Keep data flow, permissions and contracts.

### Why

alayala reported that the running app looks very different from the prototype. [YOU] traced the cause in the code. The app was not run, so the visual result is inferred, not observed.

Confirmed by reading the code:

1. The tokens are correct. `frontend/src/styles/tokens.css` matches the prototype, and `frontend/index.html` loads Geist. They are not the cause.
2. All shell and page styles are in one 49-line global file, `frontend/src/styles/app.css`. It uses a different layout model: white sidebar and gray main (prototype: `#F0F0F0` sidebar, white main), a `.panel` card around every block, an orange chart line and meter (prototype: slate), content 1500px centered (prototype: 1248px left-aligned, `Trinity.dc.html:136`), and a 64px context bar (prototype: 52px, line 115).
3. Global element rules break layouts: `label` is a flex column, `input` has `min-height: 40px` (this also hits checkboxes), `table` has `min-width: 720px`, and `h2` keeps weight 700 (prototype: 600). The `app-shell` class in `shell/AppShell.tsx` has no style. The frontend design called for CSS Modules; pages and the shell do not use them.
4. Built components are not used: Segmented, Tabs, Switch, Field, Toast (provider not mounted), TextLink, TextButton, Tag, UnavailableValue, EmptyState and the large badge. The date helpers `formatDay`, `formatShortDay` and `formatDayRange` in `lib/dates.ts` are not used, so pages show raw ISO dates.
5. Pages show machine codes: `reason_code` and `blocker.code` in `Refresh.tsx`, `d.code` as a callout title in `shared.tsx`, and text such as "Review: not_required · Publication: published".

Inferred: items 2–5 together explain the reported look. V0 screenshots will confirm this before changes.

### Scope

In: CSS (base styles and new CSS Modules for the shell and each page), component use, markup structure, copy, date formats, a single copy map for codes, mounting the existing `ToastProvider`, updated tests and screenshots.

Out: backend, API, contracts, permissions, dependencies and lockfile. No behavior change other than copy and presentation. TanStack Query usage, retries and polling stay. Charts stay hand-written SVG. No fixtures or prototype controls in the build.

### Slices

| Slice | Change | Pages touched |
|---|---|---|
| V0 | Baseline capture: Playwright screenshots at 1440 and 924px with the synthetic API, next to the handoff screenshots | all (read-only) |
| V1 | Base styles: remove global element rules, swap surfaces, 1248px left-aligned content, tokens, CSS Modules; keep `base.css` helpers | all |
| V2 | Shell: logo, nav labels and groups, Refresh count, account block, context bar, drawer under 960px | shell |
| V3 | Dashboard: title, KPI row with dividers, meter, Segmented range, Tabs, chart, daily values, selected observation, contributions | Dashboard |
| V4 | Catalog grid rows and Table view breadcrumb, filters, table | Catalog, Table view |
| V5 | SQL Explorer: Tables aside, editor, footer bar, results states, schema panel | SQL |
| V6 | Refresh list, Run detail timeline and candidate review | Refresh, Run detail |
| V7 | Settings column, Switch, Fields, Save state; setup page | Settings, Setup |
| V8 | Sign-in card and Waiting / no-publication state | Sign-in, Waiting |
| V9 | Undesigned states from the pattern map; copy map turns raw codes into sentences | all |
| V10 | Verification: typecheck, lint, test, build, e2e configs, 1440/924 screenshots compared per S25, difference list | all |

Step 1 of every plan: **Maintain data evidence — ongoing.** This change makes no EIA calls. Mock values are design examples, not findings.

### Contract differences kept

The contracts win over the mock (A25). These mock details stay different on purpose:

- No Rows column in the Catalog (R32). No "Illustrative data" pill (R05; `scripts/check-build.mjs` blocks it).
- IDs show the first 8 characters in mono with a tooltip; runs show "Run #N" (R21). "run-1044" and "pub-2026-09-28-a" are design examples.
- Viewer sees no facility contributions (R29, S11).
- Range labels follow R23 ("Last 365 days"), unless the spec records a deliberate change.
- Warning callouts show the server `message` (R22). The KPI heading uses `summary.period` (R24).
- Missing values never show as zero.

### Undesigned states

Build them only from patterns that exist in the prototype. Show screenshots to alayala. No Material Design and no new visual vocabulary.

| Need | Pattern |
|---|---|
| Blocking problem | error callout |
| Needs attention | warning callout |
| Neutral info or progress | info callout or muted inline text |
| No rows | dashed `EmptyState` box |
| Lifecycle status | `Badge` pill |
| Confirmation | existing `Dialog` |
| Brief success | `Toast` (mount `ToastProvider`) |

The brief lists every state per area (session, errors, dashboard, tables, SQL, refresh, settings). The spec owns the full list (UF-X*).

### Risks

- **Global rule removal.** Removing `label`, `input`, `table` and `h2` rules can break forms and tables that depend on them. Mitigation: V1 first, then screenshots of every page before page slices.
- **Test copy updates.** `frontend/src/pages/pages.test.tsx` asserts old copy ("Overview", "Save schedule", "Offline share over time"). Update the tests with the copy, and do not weaken what they check.
- **Fonts offline.** Geist loads from Google Fonts. Without network, the stack falls back to `system-ui` and screenshots differ. Record the font state with each screenshot.
- **Chart rewrite.** Restyling the chart can break keyboard pinning, `aria-live` updates and reduced motion. Keep the existing behavior and its tests; change visuals only.
- **Responsive.** Keep the 960px drawer breakpoint (R63) and no page scroll at 320px.

### Acceptance

- Each requirement in [spec.md](spec.md) (UF-B*, UF-S*, UF-D*, UF-C*, UF-Q*, UF-R*, UF-T*, UF-A*, UF-X*) has evidence.
- V10 meets UF-V* and frontend S25: screenshots at 1440 and 924px, each difference marked "accepted contract difference" or "fixed".
- Typecheck, lint, unit tests, build with `check-build`, and the presentation, explorer and session e2e configs pass. Report any check that did not run.
- Focus-visible, `aria-live`, keyboard chart and reduced motion still work.

### Attribution

Per [A25](../../DECISIONS.md#a25--figma-design-and-brand-handoff) and [NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026): [ME] alayala created the interface mockups in Figma. The brand reference was made with ChatGPT. This change does not credit AI with the original design.

- [ME] alayala: requested the change, waived per-screen approval, approved the pattern approach, reviews undesigned-state screenshots and the V10 difference list, and commits.
- [YOU] OpenCode agents: traced the root cause, drafted these SDD documents and will implement presentation changes. AI code and copy changes are recorded separately from his design.
