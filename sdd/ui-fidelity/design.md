# Design: UI fidelity to the explorer handoff

Date: 2026-10-06
Status: Draft. [YOU] OpenCode drafted this design; [ME] alayala requested the change. Not reviewed yet.
Branch/inspection: `ui/handoff-fidelity`, HEAD `bf52757`. The app was not run for this design; facts below come from reading the code.
Basis: [proposal](proposal.md), [spec](spec.md) (UF-* requirements), [frontend design](../frontend/design.md), [handoff prototype](../../docs/design-reference/2026-10-04-explorer-handoff/Trinity.dc.html), A9, A16, A19, A20 and A25 in [DECISIONS.md](../../DECISIONS.md).
Design attribution: alayala created the mockups in Figma. The brand reference was made with ChatGPT. See [NOTES.md](../../NOTES.md#figma-mockups-brand-and-claude-handoff--october-4-2026). This document only describes how to build that design.

## Human

### What will change

The app keeps its data, queries and permissions. Only styles, layout and visible text change.

1. **Styles move next to their code.** Each page and the shell get their own `*.module.css` file. The global `app.css` file is removed step by step. Global CSS keeps only tokens, a reset and four layout helpers.
2. **Built components are used.** Tabs, Segmented, Switch, Field, Tag, EmptyState, TextLink and the large badge already exist. Pages start to use them. A few small new display components fill the gaps (KPI row, meter, list rows, bar list, step timeline).
3. **Machine codes become sentences.** One module, `frontend/src/lib/copy.ts`, turns codes such as `refresh_active` into plain sentences. No raw code is shown on screen.
4. **Dates use the date helpers.** "2026-09-27" becomes "27 Sep 2026".

Example: Admin opens Refresh while a run waits for review. Today the page shows `review_required` under the button. After this change it shows "Resolve the candidate awaiting review first." (spec UF-X10). The sidebar shows a count "1" next to Refresh, and the context bar shows a warning pill that links to the run.

Failure case: the server sends a new `reason_code` that the frontend does not know. The page shows "This action is not available now." It does not show the code.

### What stays the same

API calls, TanStack Query keys, retries, polling, ETags, idempotency keys, capability guards, the 960px drawer breakpoint, keyboard behavior, reduced motion and `scripts/check-build.mjs`. No new package.

## LLM

### 1. Styling architecture

**Final global CSS (imported by `frontend/src/main.tsx`):**

- `styles/tokens.css`: unchanged. It already matches the prototype tokens.
- `styles/base.css`: keeps the reset, focus outline, `.tabular`, `.mono`, `.sr-only`, `.page-enter` and reduced motion. It gains four layout helpers moved from `app.css` (`.stack`, `.row`, `.spread`, `.muted`). It gains one heading reset: `h1, h2, h3 { font-weight: 600; line-height: 1.2 }`. This replaces the browser default of 700. Sizes stay in modules.
- `styles/app.css`: deleted after the last slice moves its last selector. The `./styles/app.css` import in `main.tsx` is removed in the same step.

**Rules for modules.** A module uses only `var(--…)` tokens, no raw colors. Static styles go in the module. Inline `style` is allowed only for computed geometry (left, width, top, height). Tests never select by class name, because Vitest hashes CSS Module names. Where a test needs a hook, the element gets a `data-part` attribute (for example `data-part="outlier"`).

**Order of removal.** V1 deletes the element rules first (`h1–h3`, `label`, `input/select/textarea`, `table/th/td`) and applies `Field`, `inputClass` or `filterInputClass` to every existing control in the same slice. No control is left without a style between slices. Each later slice moves its own class selectors out of `app.css`.

| `app.css` selector (line) | New home | Slice |
|---|---|---|
| `.stack`, `.row`, `.spread`, `.muted` (1–4) | `styles/base.css` layout helpers | V1 |
| `.panel` (5) | Removed. Page modules define the few real surfaces: `Dashboard.module.css .selectedPanel`, `Refresh.module.css .summaryStrip/.candidateCard`, `SqlExplorer.module.css .schema` | V1, then V3/V5/V6 |
| `h1`, `h2`, `h3` (6) | `components/layout/PageHeader.module.css .title`; page modules `.sectionTitle`; weight reset in `base.css` | V1 |
| `label` (7) | Removed. `components/controls/Field.module.css .field` | V1 |
| `input,select,textarea`, `input:disabled` (8–9) | Removed. `Field.module.css .input/.filter` via `inputClass`/`filterInputClass`; SQL textarea in `SqlExplorer.module.css .textarea`; checkbox replaced by `Switch` | V1 |
| `.wordmark` (10) | `components/brand/BrandLockup.module.css` | V2, V8 |
| `.sign-in`, `.sign-in form` (11–12) | `pages/signin/SignIn.module.css .page/.card` | V8 |
| `.sidebar`, `.pinned`, `.sidebar nav`, `nav a`, `a.active`, `.account`, `.workspace`, `.context-bar`, `.ready`, `.content`, `.menu-button`, `.drawer-backdrop`, `.drawer`, `@media 959px`, `drawer-enter` (13–25, 33, 48–49) | `shell/AppShell.module.css`. `.ready` becomes a `StatusBadge`. The undefined `app-shell` class becomes `.shell` | V2 |
| `.table-scroll`, `table`, `th,td`, `th`, `tbody tr:hover` (26–30) | `pages/shared.module.css` (exported for `DataTable` and the daily values table). No global `min-width`; each table sets its own | V1 |
| `.filters` (31) | `pages/catalog/Catalog.module.css .filters`; `Dashboard.module.css .customRange` | V3, V4 |
| `.empty` (32) | Removed. `EmptyState` (`States.module.css .empty`) | V4, V6 |
| `.sql-layout`, `.editor`, `.editor pre/textarea`, `@media 1100px` (34–38) | `pages/sql/SqlExplorer.module.css` | V5 |
| `.kpis`, `.hero-value`, `.kpi-value`, `@media 760px` (39–40, 43) | `components/data/KpiRow.module.css` | V3 |
| `.meter`, `.meter span` (41) | `components/data/Meter.module.css` (slate fill) | V3 |
| `.national-chart`, `text`, `.gridline`, `.chart-line`, `.chart-dot`, `.outlier`, `.crosshair`, `.hatch`, `.sparkline`, `chart-reveal` (42, 44–47) | `pages/dashboard/Chart.module.css`. `.spark-values` is unused and is dropped | V3 |
| `.settings-form` (44) | `pages/settings/Settings.module.css .form` (420px) | V7 |

**Shell surfaces.** `body` stays `--color-bg` (#F0F0F0), which is also the sidebar color. The workspace is `--color-surface` (white). Content uses `padding: var(--content-padding)`, `max-width: var(--content-max)` (1248px), `width: 100%` and no auto margin, so it is left-aligned.

### 2. Components

**Reused as they are (props unchanged unless stated):** `Button` (`size="compact"` for 34px, `size="small"` for 28px, `size="full"` for sign-in, `variant="destructive"` for red-text Discard), `ButtonLink`, `TextLink`, `TextButton`, `Segmented`, `Tabs`, `Switch`, `Field` + `inputClass`/`filterInputClass`, `ShortId`, `StatusBadge` (with `large` on run detail), `Tag` (Latest/Pinned), `MissingChip`, `UnavailableValue`, `Callout`, `EmptyState`, `LoadingRows`, `ErrorState`, `NothingToShow`, `ConfirmDialog`, `ToastProvider`/`useToast`.

**Toast mount point.** `main.tsx` wraps `<App />` in `<ToastProvider>` inside `SessionProvider`. `useToast` has a no-op default, so unit tests that render pages without the provider still work.

**New presentational components.** They receive values and callbacks only. They do no data fetching and no decimal arithmetic. Each gets a docstring that follows CONTRIBUTING.md.

| Component | File | Props |
|---|---|---|
| `PageHeader` | `components/layout/PageHeader.tsx` + `.module.css` | `title: ReactNode`, `subtitle?: ReactNode`, `aside?: ReactNode`, `breadcrumb?: ReactNode`, `mono?: boolean` |
| `BrandLockup` | `components/brand/BrandLockup.tsx` + `.module.css` | `size: 'nav' \| 'signin'` (mark 28/36px, letters 84/112px, uppercase caption 9.5/11px) |
| `KpiRow` | `components/data/KpiRow.tsx` + `.module.css` | `items: { label: string; value: ReactNode; unit?: string; hero?: boolean }[]`. Columns split by 1px `--color-border-2` lines, no cards |
| `Meter` | `components/data/Meter.tsx` + `.module.css` | `width: string` (CSS percent, clamped by the caller), `label: string` (aria), `outOfRange: boolean`, `legend?: ReactNode`. 10px track, slate fill |
| `MetaList` | `components/data/MetaList.tsx` + `.module.css` | `items: { term: string; detail: ReactNode }[]`, `layout: 'grid' \| 'inline'` (a `<dl>`) |
| `ListTable` | `components/data/ListTable.tsx` + `.module.css` | `columns: { header: string; track: string; align?: 'start' \| 'end' }[]`, `rows: { key: string; to: string; label: string; cells: ReactNode[] }[]`, `rowHeight: 50 \| 52`. Each row is one `Link` with a CSS grid and a trailing "→" |
| `BarList` | `components/data/BarList.tsx` + `.module.css` | `items: { key: string; label: string; value: ReactNode; width: string; selected: boolean }[]`, `onSelect(key)`, `header: [string, string]`. Grid `120px \| bar \| 96px`, 8px slate bars, `aria-pressed` |
| `StepTimeline` | `components/data/StepTimeline.tsx` + `.module.css` | `items: { key: string; state: 'done' \| 'running' \| 'failed' \| 'attention' \| 'pending'; title: string; description: ReactNode; meta?: string; children?: ReactNode }[]`. 24px circle with glyph and an aria label from `copy.ts` |

`ListTable` accessibility: the visual header row is `aria-hidden`. Each link's accessible name is `label` plus the cell text, so a screen reader hears the full row. The rows sit in a `<ul>`.

**Page-local components (used once, so they stay in the page folder):** `pages/sql/SqlEditor.tsx` (gutter, textarea, footer slot), `pages/sql/SchemaTree.tsx` (expandable 34px rows, local open state), `shell/Sidebar.tsx` (sidebar, drawer, avatar span), `shell/ContextBar.tsx`. A separate `Avatar` or `Pill` component is not needed: each is one styled span in `AppShell.module.css`.

### 3. Shell

**Structure.** `AppShell` renders `.shell` → fixed `Sidebar` (224px, `--color-bg`, right border `--color-border`) + `.workspace` (white) → sticky `ContextBar` (min-height `--context-bar-height`, 52px) → `<main className={styles.content}>` with `<Outlet />`.

**Sidebar.** `BrandLockup size="nav"`; main nav; an "Administration" group label (11px, 0.08em, uppercase, `--color-muted-2`) shown only when at least one admin item is visible; spacer; account block. Nav items are `NavLink`s, 36px, ink, weight 500. The active item (`NavLink` `className` callback `isActive`) gets a white background, a `--color-nav-border` border and weight 600. `NavLink` already sets `aria-current="page"`. Account block (spec UF-S06): 30px slate circle with the first letter of `user_id`, `user_id` (bold, ellipsis, full value in `title`) over the role label (muted), and `Button size="small"` "Sign out".

**Nav model** in `session/capabilities.tsx`: add `group: 'main' | 'admin'` to each `navigation` item. Labels: Dashboard (`national:read`), Catalog, SQL Explorer (main); Refresh, Settings (admin). Routes and `RequireCapability` do not change.

**Refresh count.** No list of runs awaiting approval exists in `/me`. `/me` has `admin_context.active_run: RefreshSummary | null`. A16 runs the refresh lifecycle one run at a time, so at most one run can await approval. The helper `awaitingReviewCount(me)` in `shell/Sidebar.tsx` returns 1 when `me.admin_context?.active_run?.status === 'awaiting_approval'`, otherwise 0. The pill shows only for 1. It has sr-only text " run awaiting review". The count is as fresh as `/me`. The session already refreshes `/me` after commands and run status changes. No new polling is added.

**Context bar.** `ContextBar` reads `me.publication`. With a publication: "Publication" + `ShortId`, "Published" + `formatUtcTime`, "Latest observation" + `formatDay`, then `StatusBadge tone="success" glyph="●"` "Ready". Without one: "No publication yet" + `StatusBadge tone="neutral" glyph="○"` "Unavailable". Then a flex spacer, then the review pill (26px, warning colors) when the count is 1. The pill is a `Link` to `/refresh/{run_id}`. Its text uses the plain `shortId()` string, not the `ShortId` button, because a button inside a link is invalid. No "Illustrative data" tag (R05, `check-build.mjs`).

**Drawer** (below 960px). Behavior is kept: conditional mount, `useFocusTrap` (focus in, Tab cycle, Escape closes, focus returns to "☰ Menu"), backdrop `onMouseDown` closes, nav click closes. Styles move to the module: fixed panel with `transform` slide-in (`--duration-drawer`, `--ease-enter`), backdrop `--color-backdrop`, `--shadow-drawer`. The menu button keeps the visible name "☰ Menu", because `session.test.tsx` and `session.spec.ts` find it by that name.

### 4. Dashboard chart

**Layout.** `NationalChart` becomes a CSS grid: `grid-template-columns: var(--gutter) minmax(0, 1fr)`. Row 1: Y gutter + plot (260px). Row 2: empty cell + 24px X label row. `--gutter` is `max(44px, longest tick text × 7px + 10px)`, set inline, so extreme shares such as "-2500%" still fit.

**Layers in the plot (back to front):** HTML gap bands → SVG → HTML tooltip.

- **Gap bands:** absolutely positioned `div`s with `background: var(--gap-hatch)` and dashed `--color-gap-border` sides. The token is used directly, so the SVG `<pattern>` is removed. `data-part="gap"`.
- **SVG:** `viewBox="0 0 {width} 260"`. The existing `ResizeObserver` keeps `width` equal to the shown width, so 1 unit = 1px. It contains gridlines (`--color-grid`), the 2px slate line, 6px dots for single-day segments, outlier rings (`data-part="outlier"`), transparent hit columns, the crosshair, the hover dot (10px, white, slate border) and the pinned dot (12px orange with white border and 1px slate ring). Plot left is now 0, because the gutter is outside the SVG.
- **Y mapping:** `y(value) = 254 - positionBetween(value, min, max, 248n)`. The 6px inset keeps the pinned dot inside the plot. Gutter labels use the same `y()` with `translateY(-50%)`, 11px, `--color-muted-2`.
- **X labels:** a new pure function `xTickIndexes(count, plotWidth)` in `chartGeometry.ts` returns `[0, round((n-1)/3), round(2(n-1)/3), n-1]`. Below 480px plot width it returns only the first and last index, so labels do not overlap at 320px. Labels use `formatShortDay`, or `formatDay` when the range has more than 120 days. The first label is left-aligned, the last right-aligned, the others centered.
- **Tooltip:** a positioned HTML card (white, `--color-tooltip-border`, `--radius-panel`, `--shadow-tooltip`, 12.5px) at `top: 8px`, `left: x(active)`. It sits right of the point under 14% of the plot width, left of it over 86%, else centered (spec UF-D10). It shows `formatDay(date)`, share, outage MW and capacity MW, or "○ Not reported", and the out-of-range note. It appears for hover and keyboard focus, never during the range morph. It is `aria-hidden`; the existing `aria-live` text stays the one announcement, to avoid two announcements.

**Kept as is:** `chartDomain()` in `chartGeometry.ts`, the decimal domain morph (650ms, off under reduced motion), segment splitting, the keyboard model (←/→ move, Enter pins, Escape clears pin and hover, as R26 and the current tests require), `role="application"` and its label, and `onSelect`.

**Sparkline** (`Sparkline.tsx`): 64px high, `viewBox="0 0 300 64"`, width 100% up to 360px. HTML gap bands with `--gap-hatch` at percent positions, a bottom baseline in `--color-border-2`, white dots with a 1.5px slate border, slate segments. Below: `formatShortDay` start and end labels and the caption "Reported outage MW, {range}. Gaps stay empty." (spec UF-D21). The data passed in does not change.

**Rest of the dashboard** (`Dashboard.tsx`, `Dashboard.module.css`): `PageHeader` with a `MetaList layout="grid"` aside (Publication, Published, Observation). Sections separated by a top border, not cards. `KpiRow` + `Meter` + legend + formula line. Chart section: `Tabs` (Chart / Daily values), `Segmented` range (`30d`, `90d`, `1y`, custom) and a range label from `formatDayRange` + `daysInclusive`. `Dashboard` passes the range controls into `DashboardData` as a `rangeControls` prop, so they sit in the chart section; while the first load is pending or failed, `Dashboard` renders them above the loading or error state. The visible "Selected range loaded." text becomes `sr-only`; the live region stays (`explorer-state.test.tsx` still finds it). While a range updates, a muted "Updating…" text appears beside the range label. Daily values: 420px scroll box, sticky header, rows pin on click, the day cell keeps a `TextButton` for keyboard use, `Tag` Latest/Pinned. The selected panel uses `--color-surface-2` and keeps its heading element. The "Latest observation" button is always shown and is disabled when nothing is pinned. Contributions: `BarList` left; detail column with a left border, `Sparkline` and two `TextLink`s; shown only with `preview:detail` (R29).

### 4a. Other pages

Each page keeps its hooks and handlers. Only the returned markup and its module change.

- **Catalog + Table view (V4):** `Catalog` uses `PageHeader` and `ListTable` (52px rows: Table key in mono, Dataset = `label`, Latest observation, "→"; spec UF-C02). No Rows column (R32). `TableView` uses a breadcrumb `TextLink` "Catalog" / key, a sans title from `dataset.label`, and a subtitle with `ShortId` and the description. Filters sit in one row: `Field compact` + `filterInputClass` (34px, 12px muted labels), "Apply dates" and "Reset filters" as `Button size="compact"`, a spacer, then the row count on the right. `FacilityChoices` and `GeneratorChoices` render their fields inline in that row. `DataTable` header has no fill (12px muted), body 14px, `--color-border-3` row lines, its own `min-width: 720px`.
- **SQL (V5):** `PageHeader` with a "Tables ▾" toggle (`aria-expanded`, local state, open by default). Flex row: editor (`flex: 1 1 560px`) and `SchemaTree` aside (272px). `SqlEditor`: 8px radius, `--color-editor` background, border turns slate on `:focus-within`; 40px gutter on `--color-surface-3` with a right border; 13.5px mono, 22px line height; height = lines × 22px + 28px, at least 8 lines; scroll sync kept. Footer: "Examples" + four chips "Browns Ferry", "Empty result", "Error", "Generators" (spec UF-Q04; each inserts real SQL), spacer, "⌘/Ctrl + Enter", `Button variant="primary" size="compact"` Run query. Results: `h2` "Results" with a right `role="status"` meta ("N rows · X ms"). `DataTable sql` gets mono text, sticky header and a 440px scroll box.
- **Refresh + Run detail (V6):** `RefreshList` uses `PageHeader` (Start refresh as aside), a muted disabled reason from `blockReason()`, a summary strip (Current publication, Awaiting review, fixed sentence) and `ListTable` (50px rows: run `shortId`, Started (`requested_at`), `RunBadge`, Finished). `RunPage` uses a 28px mono "Run #N" title with `RunBadge large`, a subtitle from `RUN_STATUS[status].summary` + `formatUtcTime`, and `StepTimeline`. The timeline has one item for "Accepted", one per `STEP_STAGES` stage: Retrieve, Prepare, Validate, Publish (state from the latest attempt; older attempts and `error_summary` as children; "Show more attempts" kept). Review is shown on the Publish row ("Waiting on you.", attention state) and on the candidate card, not as its own row (spec UF-R06, R50). `CandidatePanel` becomes a card (`--radius-dialog`, 24px padding, 760px): "Candidate" + `ShortId`, warning callouts, the checks count, `candidateCopy()`, the current-publication sentence, Approve (primary), Retry publication, Discard (`variant="destructive"`) and the discard note.
- **Settings (V7):** `PageHeader` "Schedule" or "Set up Trinity". A bare 420px column: a `Switch` row (label `id` from `useId`, a subtitle sentence from the form values, bottom divider), `Field` Time and Timezone with `inputClass`, the clock note, and a Save row with a `role="status"` text ("No unsaved changes." / "Unsaved changes." / the notice). Schedule status is one 13px muted line under the Save row, "Next scheduled check: …" via `formatLocalTime` (spec UF-X11); its blocker is a warning callout.
- **Sign-in + Waiting (V8):** `SignIn.module.css .card`: 400px, `--radius-dialog`, 32px padding, border, white on `--color-bg`. `BrandLockup size="signin"`, the brand line, `Field` + `inputClass`, `Button variant="primary" size="full"`. The startup error renders inside the same card. `Waiting` passes a secondary `ButtonLink` "Go to Refresh".

### 5. Copy map

New module `frontend/src/lib/copy.ts`. It holds pure functions and typed records only.

| Export | Input | Use |
|---|---|---|
| `BLOCK_REASONS: Record<BlockCode, string>`, `blockReason(code)` | `Action.reason_code` | disabled reason under Start refresh and other actions |
| `blockerTitle(code)` | `Blocker.code` | callout title; the body is the server `Blocker.message` |
| `RUN_STATUS: Record<RunStatus, {tone, glyph, label, summary}>` | run status | `RunBadge`, run subtitle sentence (the table moves from `Refresh.tsx`) |
| `STAGE_LABELS`, `STEP_STATE: Record<StepStatus, …>` | step stage and status | `StepTimeline` titles and circle labels |
| `REVIEW_STATUS`, `PUBLICATION_STATUS` | candidate enums | replaces "Review: x · Publication: y" |
| `candidateCopy(candidate)` | `Candidate` | moved unchanged from `Refresh.tsx` with its 10 messages |
| `ROLE_LABELS`, `metricReason(reason)` | role, `MetricNullReason` | account block; null KPI text |
| `receiptToast(action)` | `ActionName` | toast after an accepted command |

**Unknown codes.** Lookup uses `RECORD[code as BlockCode] ?? GENERIC` with a fixed sentence such as "This action is not available now." The raw code is not put in a `title` attribute. Reason: a title is visible on hover and some screen readers read it, so the code would still reach the user. Support uses the request ID (R59 pattern), and the code stays visible in the network response. Typed `Record`s make TypeScript fail when an enum value has no entry. The existing OpenAPI enum test in `api/types.test.ts` fails when the contract adds a value. So the fallback is only a safety net.

**Diagnostics** (`Diagnostics` in `pages/shared.tsx`): the callout title becomes the fixed text "! Warning". The body stays the server `message` (R22). `d.code` is no longer shown. Step `error_summary` and `Blocker.message` are server text and stay; `error_code` is never shown. API errors keep using `errorMessage()` in `api/messages.ts`.

### 6. Dates

Every date goes through `lib/dates.ts`. Calendar dates (`period`, `latest_observation_date`, range ends) use `formatDay`, `formatShortDay` or `formatDayRange`. Event times (`published_at`, `requested_at`, `finished_at`) use `formatUtcTime`. Durations use `formatDuration`. One new helper is needed: `formatLocalTime(text)` for `ScheduleStatus.next_check_local`, which is RFC 3339 with the offset of the configured timezone. It reads the wall-clock digits from the text with a regular expression and does not create a `Date`. A browser in another zone therefore cannot shift it (R19). Unreadable text is returned unchanged, as `formatUtcTime` does.

### 7. Pattern map for states without a design

| Meaning | Build with | Examples |
|---|---|---|
| Blocking problem | `Callout tone="error"` (`PageError`, `ErrorState`), "✕" title | startup error + Retry, 403/404, query error, run failed, publication failed |
| Needs attention | `Callout tone="warning"`, "!" title | blocker, logout unconfirmed, 412 changed, lost save response, review warnings |
| Neutral info or progress | `Callout tone="info"` or muted inline text | session ended, updating range, publication changed restart, 1,000-row truncation, partial table footer |
| No rows | `EmptyState` (dashed) | no runs, no rows match, query returned 0 rows, idle SQL, dataset not found (+ `TextLink` to Catalog) |
| Lifecycle status | `StatusBadge` | Publishing, Publication failed, Superseded, Discarded |
| Confirmation | `ConfirmDialog` | Start refresh, Approve, Discard, Retry publication, Run again, Resolve warning |
| Brief success | `useToast` | accepted refresh commands (from `useCommand` in `Refresh.tsx`) |

Controls in these states use existing parts: `ReadRetry` stays a secondary `Button` beside its callout; "More facilities", "Load more", "Load all rows", "Show more attempts" and "Load older" use `Button size="compact"`; the 429 countdown stays in the Run query label. No new visual vocabulary.

### 8. Testing

**Unit (Vitest):**

- New `lib/copy.test.ts`: every value of `BLOCK_CODES`, `RUN_STATUSES`, `STEP_STATUSES`, `STEP_STAGES`, `REVIEW_STATUSES`, `PUBLICATION_STATUSES` and every role has a non-empty sentence without an underscore; an unknown code returns the generic sentence; `candidateCopy` keeps its 10 outputs.
- New `expectNoRawCodes(container, allow)` helper in `src/test/`. It fails when visible text contains a snake_case token. `allow` lists dataset keys, column names and `user_id`. Use it in Refresh list, Run detail (awaiting review, failed, publishing) and Settings tests.
- `lib/dates.test.ts`: cases for `formatLocalTime`. `chartGeometry` cases for `xTickIndexes`.
- Update existing tests for changed copy and structure: `pages.test.tsx` (nav link "Schedule" → "Settings"; any save label the spec changes; refresh reason sentence), `presentation.test.tsx` (viewBox `0 0 222 260`; `.outlier` → `[data-part="outlier"]`). Shell test: nav groups, count pill only for `awaiting_approval`, drawer focus return.

**Browser (Playwright, synthetic API):** new `tests/e2e/fidelity.config.ts` + `fidelity.spec.ts` + `fidelity-fixtures.ts`. They follow the `presentation.config.ts` pattern: running dev server on 5173, `page.route('**/api/v1/**')` with contract-shaped synthetic responses, a synthetic session token, reduced motion. Output: `../../test-results/ui-fidelity-<stage>`, where `TRINITY_FIDELITY_STAGE` is `v0-baseline`, a slice ID or `v10-final`. Each page state is captured full-page at 1440×900 and 924×900 and named after its handoff screenshot (for example `13-run-review-1440.png`). A 320px pass checks that `scrollWidth` ≤ the viewport width (R63). The spec waits for `aria-busy` to clear, not for new copy, so it also runs on the V0 baseline. Fixtures live under `tests/`, never `src/`, so they cannot enter `dist/`.

`presentation.spec.ts` changes: label checks read the HTML tick labels (`[data-part="tick-x"]`, `[data-part="tick-y"]`) instead of SVG `text`, and accept 11px text; date labels no longer start with "2026-"; the heading becomes "Selected observation · 4 Oct 2026". `data.spec.ts` headings change the same way; that spec needs a local publication and may not run in V10.

**Unchanged:** `scripts/check-build.mjs` and its forbidden list. New copy must not contain "Illustrative data", "PROTOTYPE" or "Continue as".

### 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Removing global element rules leaves raw controls | V1 applies `Field`/`inputClass` to every control in the same slice; V0 and V1 screenshots compared |
| Tests select by class or old copy | `data-part` hooks; copy tests updated in the slice that changes the copy |
| Chart layout change breaks label or keyboard checks | Geometry stays in `chartGeometry.ts`; keyboard handler unchanged; presentation tests updated in V3 |
| Mock values copied as contract data | Contract wins: no Rows column (R32), `Run #N` and 8-character IDs (R21), "Last 365 days" (R23), "NULL" chip in SQL (D04), no facility contributions for Viewer (R29), "Apply dates" stays. The difference list in V10 records each case |
| Count pill looks stale | It shows `/me` state, which already refreshes after commands and status changes; no new polling |
| Two live announcements on chart hover | Tooltip is `aria-hidden`; one `aria-live` text |
| Catalog description has no place in the 52px rows | It moves to the Table view subtitle; nothing is lost |

**Unchanged:** `api/*`, query keys and options, `SessionProvider`, route guards, polling intervals, command retry and idempotency, ETag handling, decimal arithmetic, publication checks in `allFacilities`, and the backend.

### Implementation notes — 2026-10-06

[YOU] OpenCode built V0–V9 in one pass on `ui/handoff-fidelity`. Differences from the plan above:

- `KpiRow`, `Meter`, `MetaList` and `BarList` stay page-local markup in `Dashboard.tsx` with `Dashboard.module.css`, because only the dashboard uses them. `SqlEditor` and `SchemaTree` stay in `SqlExplorer.tsx`. `noRawCodes.ts` became the `expectNoRawCodes` helper in `pages/pages.test.tsx`.
- `ListTable` puts the link in the first cell and stretches it over the row with `::after`. The link name stays the short key or run ID, so existing tests and screen readers hear one short name.
- `PageHeader` gained `titleAddon`, so the run badge sits beside the `h1` and does not join the heading's accessible name ("Run #4").
- Consecutive missing days draw one gap band.
- Toasts confirm accepted commands; `useToast` keeps its no-op default for tests without the provider.

### New files proposed

- `frontend/src/lib/copy.ts`, `frontend/src/lib/copy.test.ts`
- `frontend/src/components/layout/PageHeader.tsx` + `.module.css`
- `frontend/src/components/brand/BrandLockup.tsx` + `.module.css`
- `frontend/src/components/data/{KpiRow,Meter,MetaList,ListTable,BarList,StepTimeline}.tsx` + matching `.module.css`
- `frontend/src/shell/Sidebar.tsx`, `frontend/src/shell/ContextBar.tsx`, `frontend/src/shell/AppShell.module.css`
- `frontend/src/pages/shared.module.css`, `pages/dashboard/Dashboard.module.css`, `pages/dashboard/Chart.module.css`, `pages/catalog/Catalog.module.css`, `pages/sql/SqlExplorer.module.css`, `pages/refresh/Refresh.module.css`, `pages/settings/Settings.module.css`, `pages/signin/SignIn.module.css`
- `frontend/src/pages/sql/SqlEditor.tsx`, `frontend/src/pages/sql/SchemaTree.tsx`
- `frontend/src/test/noRawCodes.ts`
- `frontend/tests/e2e/fidelity.config.ts`, `fidelity.spec.ts`, `fidelity-fixtures.ts`

Deleted at the end: `frontend/src/styles/app.css`.
