# Handoff: Trinity — Nuclear Outage Explorer (desktop app)

## Overview
Trinity helps users understand U.S. nuclear outages at three levels: national, facility, and generator. This package covers the full desktop-first app: sign-in, national dashboard, catalog and table browsing, SQL Explorer, and admin refresh / review / schedule flows, with role-based navigation (viewer, analyst, admin).

Brand line: **"Three levels. One clear view."**

## About the design files
`Trinity.dc.html` is a **design reference built in HTML**. It is a working prototype that shows the intended look, copy, states, and behavior. It is not production code to copy. The task is to **recreate it in the existing Trinity React (Vite) codebase**, using that codebase's routing, state, data-fetching, and component patterns.

To view it, open `Trinity.dc.html` in a browser from this folder. It needs `support.js` and `assets/` next to it. All logic is in the `<script data-dc-script>` block at the bottom of the file. Read it for exact fixture data, formulas, and state transitions.

The designer did not inspect the existing `trinity` codebase. Map these specs onto the components that already exist there before creating new ones.

## Fidelity
**High-fidelity.** Colors, type, spacing, copy, states, and motion are final. Recreate the design pixel-accurately with the codebase's own libraries.

---

## Design tokens

### Color
| Token | Hex | Use |
|---|---|---|
| `slate` | `#243237` | Brand slate, chart lines, selected segmented controls, avatar, toggle on |
| `orange` | `#F8642B` | Logo, primary buttons, pinned chart point. Use sparingly. |
| `orange-hover` | `#F2581D` | Primary button hover |
| `orange-border` | `#E5571F` | Primary button border |
| `orange-tint` | `#FDE3D7` | "Pinned" badge |
| `orange-wash` | `#FEF3EE` | Pinned row in Daily values |
| `ink` | `#1E1D1D` | Primary text. Also the text color on orange buttons. |
| `ink-2` | `#4A4F51` | Secondary body text |
| `muted` | `#5F6366` | Labels, subtitles (≥4.5:1 on white) |
| `muted-2` | `#6B7072` | Axis labels, table headers |
| `bg` | `#F0F0F0` | App background and sidebar |
| `surface` | `#FFFFFF` | Main content surface |
| `surface-2` | `#FAFAFA` | Selected-observation panel, sticky table heads |
| `border` | `#E4E4E4` | Section rules, header and sidebar dividers |
| `border-2` | `#EDEDED` / `#EFEFEF` | Row dividers |
| `field-border` | `#D6D6D6` | Inputs, secondary buttons |
| `grid` | `#EDEDED` | Chart gridlines |
| success | bg `#E8F3EC` / fg `#1D6B3E` | Published, Ready |
| warning | bg `#FBF0E2` / fg `#8A4A0B` (callout text `#6E3B08`, border `#EBC99D`) | Awaiting review, out-of-range |
| error | bg `#FBEAE8` / fg `#A13A2C` (callout text `#7E2B20`) | Failed, query error, destructive button |
| neutral | bg `#EEEEEE` / fg `#4A4F51` | Unavailable, Discarded |
| running | bg `#E6ECEE` / fg `#243237` | Running |

Every status pairs color with a glyph and a text label: ✓ Published, ✕ Failed, ! Awaiting review, ◐ Running, – Discarded, ○ Not reported / Unavailable, ● Ready.

### Typography
- Sans: **Geist** (400/500/600/700). Mono: **Geist Mono** (400/500) for SQL, table names, and publication or run IDs. Both are on Google Fonts.
- Page title: 32px / 600, letter-spacing −0.025em, line-height 1.15.
- Section title (H2): 19px / 600, letter-spacing −0.01em.
- Body: 14–15px. Secondary: 12.5–13px. Table header: 12px / 500, color `muted`.
- Hero KPI: 48px / 600, letter-spacing −0.035em. Secondary KPIs: 28px / 500.
- Use `font-variant-numeric: tabular-nums` on every metric, table, and date.

### Spacing, radius, elevation
- 8px base unit. Content padding 32px. Sidebar width 224px. Max content width 1248px.
- Sections are separated by a 1px `border` top rule, 40px above and 24px below. Content is grouped with rules and spacing, not a card per number.
- Radius: 6px for buttons and inputs, 8px for panels and tables, 10px for dialogs and the sign-in card, 4px for badges.
- Shadows: tooltip `0 4px 16px rgba(30,29,29,.08)`. Dialog `0 16px 48px rgba(30,29,29,.18)`. Drawer `0 12px 40px rgba(30,29,29,.18)`. Nothing else has a shadow.
- Control heights: buttons 36px (compact 32–34px, tiny 26–28px), inputs 40px (filters 34px), table rows about 44–52px.

### Components
- **Primary button:** orange background, `ink` text at 600 weight, 1px `orange-border`. Hover `orange-hover`. Disabled at opacity .45 with `not-allowed`.
- **Secondary button:** white background, `field-border` border. Hover border becomes `slate`.
- **Destructive button:** white background with red text (Discard), or solid `#A13A2C` with white text in the confirmation dialog.
- **Segmented control** (ranges, prototype role switch): selected is `slate` background with white text; unselected is white.
- **Tabs:** text tabs with a 2px `slate` underline on the selected tab. Selected text is `ink` at 600; unselected is `muted` at 500.
- **Focus:** global `:focus-visible { outline: 2px solid #F8642B; outline-offset: 2px }`.
- **Missing-value chip:** dashed 1px `#A9AEB0` border, `ink-2` text, label "○ Not reported" (in SQL results: "NULL · not reported").
- **Unavailable value:** plain `muted` text, "Unavailable".

---

## Application shell
- **Left sidebar** (224px, `bg`, right border `border`, sticky full height):
  - Logo (orange mark `assets/mark-orange.png` at 28px plus `assets/wordmark-letters.png` at 84px, with "OUTAGE EXPLORER" in 9.5px caps underneath).
  - Navigation. Selected item: white background, `#E0E0E0` border, weight 600.
  - "Administration" group label, shown to admins only. The Refresh item shows a count pill when a candidate awaits review.
  - Account block: avatar initial, account name, role, and a Sign out button.
- **Top context bar** (sticky, at least 52px tall, bottom border):
  - With a publication: Publication `pub-…` (mono, nowrap) · Published `28 Sep 2026, 14:10 UTC` · Latest observation `27 Sep 2026` · ● Ready badge.
  - With no publication: "No publication yet" · ○ Unavailable.
  - Admins with a pending candidate see an "! ver-19c awaits review" pill that links to the run.
  - Right side: "Illustrative data" tag.
- **Role visibility** (navigation only; this is not authorization):
  - Viewer: Dashboard.
  - Analyst: Dashboard, Catalog, SQL Explorer.
  - Admin: all of the above plus Refresh and Settings.
  - If the current role can't see a page, redirect to Dashboard.
- **Below 960px:** the sidebar becomes an off-canvas drawer opened by a "☰ Menu" button. A backdrop closes it, and so does Escape.
- **Prototype controls** (dashed-border box at the bottom of the sidebar and below the sign-in card): role switch and data state (Published / Unpublished). These are for demos only. Keep them behind a dev flag or drop them in production.

## Screens

### A. Sign-in
- Centered card, max width 400px. Logo lockup, then "Three levels. One clear view." (20px / 500, `slate`), then "Sign in with your account."
- Fields: Account, Password. Primary full-width "Sign in" button.
- Footer line: "Already set up: viewer, analyst, admin."
- Prototype: entering viewer, analyst, or admin as the account (any password) signs in. Anything else shows an inline error: "Unknown account. Use viewer, analyst, or admin."
- Dashed "PROTOTYPE · Preview a role without credentials" box with "Continue as …" buttons.

### A2. Unavailable (no publication)
- Heading "Nothing to show yet", body "An admin still needs to publish the first set of data."
- No metrics. Applies to Dashboard, Catalog, Table, and SQL.
- Admins also see a "Go to Refresh" button. Viewers never see admin actions.

### B. National dashboard
1. **Header.** Title "U.S. nuclear fleet", subtitle "Latest published observation". On the right, a definition list: Publication / Published / Observation. Keep publication metadata and observation metadata separate.
2. **Latest observation.** Label "Latest observation · 27 Sep 2026". Three columns separated by vertical rules:
   - Fleet offline **14.4%**
   - Reported outage **14,420 MW**
   - Reported capacity **100,056 MW**

   Below them, a proportional meter: 10px tall, `#E9E9E9` track, `slate` fill at the share percentage. Legend: "Offline 14.41%" and "Remaining reported capacity 85.59% · 85,636 MW". Then the line "Offline share = reported outage ÷ reported capacity."
3. **Daily offline share.**
   - Range control: 30 days / 90 days / 365 days / Custom range. Custom shows From and To date inputs. A range label follows, for example "29 Aug – 27 Sep 2026 · 30 days".
   - Tabs on the right: Chart / Daily values.
   - Chart: 260px tall plot with a 44px y-axis gutter. Gridlines fall on round steps (5, 10, or 25 depending on span). The line is 2px `slate`.
   - **Missing days break the line.** Each gap gets a hatched band (`repeating-linear-gradient(135deg, rgba(36,50,55,.08) 0 3px, transparent 3px 7px)`) with dashed side borders. An isolated reported day renders as a 6px dot.
   - Out-of-range values (above 100 or below 0) get a white dot with a 2px `#C2670F` ring, plus a warning callout above the chart.
   - Hover shows a dashed crosshair, a hollow dot, and a tooltip. The tooltip shows the date plus Offline share, Outage, and Capacity, or "○ Not reported".
   - Click pins a point: solid line plus an orange dot.
   - Keyboard: when the plot has focus, ←/→ move, Enter pins, Esc clears.
   - Legend: "Reported offline share", "Gap = not reported", "Hover to inspect · Click to pin · Arrow keys when focused".
   - Daily values tab: scrollable table with Day, Outage MW, Capacity MW, Offline share. Rows show Latest and Pinned badges, and clicking a row pins it.
   - **Selected observation panel** (`surface-2`):
     - Date, plus a badge reading "Latest observation" or "Pinned".
     - Values: Offline, Outage, Capacity.
     - A previous-day comparison, or "Previous day (x) was not reported."
     - A "Latest observation" button that clears the pin; it is disabled when nothing is pinned.
4. **Facility outage contributions** (for the selected date).
   - Ranked list (`120px | bar | 96px` grid): name, 8px bar scaled to the largest outage, MW value or "○ Not reported". Missing rows sort last.
   - The note under the list explains that the fixture covers 4 facilities, that missing values are left out of the sum (not counted as zero), and how the fixture total compares with the national total.
   - Detail panel: facility name and its MW, share, and capacity on that date. Below that, a 64px sparkline for 20–27 Sep with gap bands and the selected-date dot in orange, captioned "Gaps stay empty".
   - Analysts and admins also get links: "Open in facility_outages →" and "View generators →". Each opens the table view filtered to that plant.
   - If the selected date has no facility rows, show an explanatory empty state.

### C. Catalog and tables
- Catalog: header "Catalog". Grid columns Table (mono), Level, Rows, Latest observation, →. Rows are buttons.

  | Table | Level | Rows |
  |---|---|---|
  | `national_outages` | Whole country, by day | 726 |
  | `facility_outages` | Plant, by day | 48,210 |
  | `generator_outages` | Unit, by day | 91,440 |

- Table view: breadcrumb "Catalog / table_name", title, and "{Level}. Rows from {pub}. Filters stay on this page."
- Filters: From, To, and Plant (Plant is hidden for national), plus "Reset filters" and a row count. Filters are stored per table; they are not global.
- Columns:
  - Facility: Day, Plant, Capacity MW, Outage MW, Offline share.
  - Generator: Day, Plant, Unit, Capacity MW, Outage MW, Offline share.
  - National: Day, Capacity MW, Outage MW, Offline share.
- The table scrolls horizontally, with a minimum width of 720px.
- Footer, facility and generator: "Combined offline share for these rows: Σoutage ÷ Σcapacity = x%". If any row is missing, show "unavailable" and say how many rows are not reported. Never average the percentages.
- Footer, national: "N days · M not reported".
- Legend line: "○ Not reported means no value was published for that day. 0 means the day was reported as zero."

### D. SQL Explorer
- Header with a subtitle stating that queries are read-only and, in the prototype, run on local fixtures. A "Tables ▾" toggle shows or hides the schema panel.
- Editor: bordered, `#FBFBFB` background, 40px line-number gutter (`#F3F3F3`), Geist Mono 13.5px with a 22px line height. Height grows with the line count.
- Editor footer: Example buttons (Browns Ferry, Empty result, Error, Generators), the hint "⌘/Ctrl + Enter", and a primary "Run query" button.
- Default query:
  ```sql
  SELECT period, facility_name, capacity, outage
  FROM facility_outages
  WHERE facility_name = 'Browns Ferry'
  ORDER BY period
  ```
- Results: "4 rows · 143 ms". Decimals display as `3480.0`. Nulls display as the chip "NULL · not reported", never as `0`.
- States:
  - Idle: "Run a query to see results."
  - Loading: three skeleton bars and the status text "Running…".
  - Empty: "The query ran and returned 0 rows."
  - Error: red callout "✕ Query error …".
  - Results over 200 rows are truncated, with a note.
- Schema panel (272px): expandable tables listing field and type in mono, with the note "Fields shown are the ones used by this prototype's fixtures, not a confirmed production schema."
  - `national_outages`: period date, capacity decimal, outage decimal
  - `facility_outages`: period date, facility_name string, capacity decimal, outage decimal
  - `generator_outages`: period date, facility_name string, generator string, capacity decimal, outage decimal
- In production, the real read-only query endpoint replaces the prototype's regex mini-parser (`execSQL`).

### E. Refresh (admin)
- Header "Refresh", subtitle "Past runs. The current publication stays up until a new candidate is approved."
- Primary "Start refresh" button. It is disabled while a run is in progress, with a reason shown beneath it. The dashed PROTOTYPE select next to it sets the next run's outcome; it is demo-only.
- Summary strip: Current publication · Awaiting review (if any) · "Failed or unfinished runs never replace the current publication."
- Run table: Run, Started, Status, Latest day.
  - run-1044 · Awaiting review · 28 Sep
  - run-1042 · Published · 27 Sep
  - run-1041 · Published · 26 Sep
  - run-1038 · Failed · —
  - run-1036 · Published · 19 Sep
- **Run detail:**
  - Back link, mono run ID with a status badge, and a summary line.
  - Steps list: Accepted → Retrieve → Prepare → Validate → Review. Each step has a 24px status circle (done = slate ✓, current = warning !, running = ◐, failed = red ✕, pending = empty), a name, a description, and a duration.
  - Review candidate panel:
    - Candidate `ver-19c` with the warning callout: "On 12 Sep the offline share is 102.40. That is outside 0–100, and it was left as-is."
    - "The current publication is still pub-2026-09-28-a."
    - Approve (primary) and Discard (destructive), with the note "Discard drops this candidate. It can't be brought back."
  - Both actions open a confirmation dialog.
    - Approve replaces the current publication. The 102.40 value is published as-is and shows a warning on the dashboard.
    - Discard marks the run Discarded. The publication is unchanged.
  - A failed run shows a red callout: "Nothing was published. {pub} remains the current publication."

### F. Settings (admin)
- Title "Schedule", subtitle "When the daily refresh runs."
- Fields:
  - "Schedule enabled": 40×24 toggle with `role="switch"`.
  - Time: 06:15.
  - Timezone: America/New_York.
- Note: "This only sets the clock. It does not start a refresh."
- Save is disabled until something changes. Status text reads "No unsaved changes." / "Unsaved changes." / "Saved…".

---

## Data integrity rules (must hold everywhere)
1. **Missing ≠ zero.** `null` means not reported; it renders as the chip, as a chart gap, as SQL `NULL`, and is excluded from sums. `0` means explicitly reported as zero.
2. **Aggregate share = Σoutage ÷ Σcapacity.** Never average percentages. If any input is missing, or the denominator is unavailable, show "Unavailable".
3. **Out-of-range values are retained** and flagged. Never clamp or "correct" them.
4. **Keep three dates distinct:** selected observation, latest observation, and publication time.
5. Charts, tables, and panels must agree for the same selection.
6. Failed or unfinished runs never change the current publication.

## Interactions and motion
All motion is disabled under `prefers-reduced-motion: reduce`.

| What | Spec |
|---|---|
| Page enter | opacity 0→1, translateY 6px→0, 260ms, `cubic-bezier(.2,.7,.2,1)` |
| Chart first draw (page enter, tab switch, new publication) | clip-path `inset(0 100% 0 0)`→`inset(0 0 0 0)`, 750ms, `cubic-bezier(.4,0,.2,1)` |
| **Chart range morph** (30/90/365/custom) | Animate the visible domain `{x0,x1,y0,y1}` from the current view to the target over 650ms with ease-out cubic. Redraw each frame from date-based x. Gridlines, gaps, and axis labels slide with it. Hover and pin are hidden during the morph. |
| **KPI count-up** | 14.4%, 14,420, and 100,056 count from 0 over 900ms (ease-out cubic) on dashboard enter and whenever the publication changes |
| Offline meter | scaleX 0→1 from the left, 700ms, 120ms delay |
| Sparkline | clip reveal, 480ms, when the selected facility or date changes |
| Contribution bars | `width` transition, 450ms |
| Chart crosshair and tooltip | `left/top` transition 90ms linear. Pinned marker 200ms. |
| **Sidebar drawer (<960px)** | translateX(−100%)→0, 300ms `cubic-bezier(.2,.7,.2,1)`, with visibility transitioned for focus safety. Backdrop fades in over 240ms. |
| Dialog | backdrop fade 160ms. Panel translateY 8px with scale .98→1 over 200ms. |
| Toast | translateY 10px→0 with fade, 240ms. Auto-dismisses after 4.2s. |
| Buttons and controls | background, border, color, and opacity transitions, 160ms |
| Settings toggle knob | translateX 0→16px, 200ms |

In React, Framer Motion or plain WAAPI/CSS transitions work well. Drive the chart morph with `requestAnimationFrame`, or with d3-interpolate on the scale domains.

## State model (suggested)
- `session`: `{ role }`
- `publication`: `{ id, publishedAt, latestObservation } | null`
- `nationalSeries[]`: `{ period, capacity|null, outage|null }`
- `facilityRows[]`, `generatorRows[]`
- `dashboard`: `{ range: '30'|'90'|'365'|'custom', customFrom, customTo, tab, hoverIndex, pinnedDate|null, selectedFacility }`
- `tableFilters[tableId]`: `{ from, to, plant }`
- `sql`: `{ text, status: idle|loading|done|empty|error, result, error, ms, schemaOpen, expanded }`
- `runs[]`: `{ id, startedAt, status: running|review|published|failed|discarded, latestDay, candidate, warning, steps[] }`
- `schedule`, `scheduleSaved`, `modal`, `toast`, `drawerOpen`

## Fixtures (illustrative)
- National: 365 days ending 2026-09-27. Capacity is 100,056 MW. Missing days: 2025-11-27, 2026-01-01, 2026-03-15, 2026-05-17/18, 2026-07-04, 2026-09-11/12/13. Latest outage is 14,420 MW.
- Candidate ver-19c: fills 12 Sep with outage 102,457 (share 102.40%) and adds 28 Sep at 14,010.
- Facilities (cap MW; outage on 20 / 21 / 26 / 27 Sep):
  - Browns Ferry: cap 3,480; outage 0 / **missing** / 1,160 / 1,160
  - Millstone: cap 2,108; outage 0 / 0 / 863 / 0
  - Palo Verde: cap 3,937; outage 1,314 / 1,314 / 0 / 1,314
  - Vogtle: cap 4,536; outage 0 / 0 / 1,120 / 1,120
- Generator units sum to their facility; see `FAC` in the script. Unit capacities are illustrative.

## Assets
- `assets/mark-orange.png`, `assets/mark-slate.png`: three-part rounded triangle mark, cut from the supplied Trinity brand board.
- `assets/wordmark-letters.png`: the "TRINITY" wordmark, from the same board.
- Use vector originals from the brand team if they exist. Do not use cooling-tower photography on analytical screens.

## Screenshots
`screenshots/` has one image per state, numbered in flow order, from sign-in through dashboard, catalog and tables, SQL (including the error state), refresh runs, review, the discard dialog, a failed run, settings, and the viewer's unavailable state. They were captured at a 924px viewport, so the sidebar shows in its collapsed drawer mode (behind "☰ Menu"). At 1440px the 224px sidebar is pinned on the left, as described in "Application shell".

## Files
- `screenshots/`: reference captures (see above).
- `Trinity.dc.html`: the full interactive prototype (template plus logic).
- `support.js`: the runtime needed to open the prototype. Reference only; not needed in the React app.
- `assets/`: logo images.
