# Tasks: QA-01 request handling

Date: 2026-10-05
Status: Implemented. Unchecked tasks are not evidence of work.

## [YOU]

### Step 1 — Inspect

- [x] Traced cancellation: `supervised_call` in `backend/src/trinity/queries/router.py` polls `request.is_disconnected()`; `cleanup` kills the container and releases the slot. Real disconnect tests exist.
- [x] Traced the client: `request()` accepts `signal`; the typed endpoint functions never pass one. `retry: false`; no Retry button.

### Step 2 — Specify

- [x] Recorded R1–R6 in [spec.md](spec.md) and the design in [design.md](design.md).

### Step 3 — Implement

- [x] Pass `signal` through the endpoint functions and every React Query call site.
- [x] Add `api/retry.ts` and use it in `main.tsx`.
- [x] Add the optional Retry to `PageError` and wire it in Dashboard, TableView and Choices.
- [x] Catalog draft dates + "Apply dates".
- [x] Lazy `/facilities` load on first focus.

### Step 4 — Test

- [x] Extend `fetchStub` to record and honour `init.signal`.
- [x] Vitest checks for R1–R6. Result: `npm test` 85 passed, 10 files (7 new checks in `src/pages/qa01.test.tsx`).
- [x] Playwright regression: three rapid preset clicks keep the last preset, the 1y and 90d requests abort, and no dashboard response is 429. Result: passed against the retained API (8.8 s).
- [x] Gates: `npm run typecheck` passed; `npm run lint` passed with 0 warnings; `npm test` passed.
- [x] Existing Analyst e2e updated for the lazy choice load and a publication-independent facility ID. Result: passed with `--timeout=90000` (22 s); the 30 s default is marginal against current live preview latency.
- [x] Viewer e2e checked: it fails on its fixed 2026-07-06 date after the 2026-10-05 publication. Pre-existing data drift; the assertion is not touched by this slice.

## [ME]

- [ ] Review the diff and the Vitest output.
- [ ] Run the Playwright test against the retained API with the test passwords.
- [ ] Decide whether to commit.
