# Design: QA-01 request handling

Date: 2026-10-05
Status: Implemented with this slice.

## Data flow

1. A page changes its query key. React Query drops the old observer.
2. The old query was created with a `queryFn` that consumed the `signal` from its context. React Query aborts that signal.
3. `request()` passes the signal to `fetch`. The browser cancels the HTTP request.
4. The Vite proxy forwards the cancel. The backend sees the disconnect, stops the query container, and releases the capacity slot.

Without step 2 the chain breaks at `api/endpoints.ts`, which is the QA-01 root cause.

## Files to change

| File | Change |
|---|---|
| `frontend/src/api/endpoints.ts` | Optional `signal` parameter for `getDashboard`, `getMetric`, `getPreview`, `getFacilities`, `getGenerators`. `runQuery` already has one. |
| `frontend/src/api/retry.ts` | New. `shouldRetry` and `retryDelay` for the 429 rule, with `AUTO_RETRY_MAX_AFTER_SECONDS = 5`. |
| `frontend/src/main.tsx` | Use the rule in the one production `QueryClient`. |
| `frontend/src/pages/shared.tsx` | `PageError` accepts an optional `onRetry`. It renders an `ErrorState` with a Retry button, or the unchanged `Waiting` screen for `data_unavailable`. |
| `frontend/src/pages/dashboard/Dashboard.tsx` | Pass `signal` from each `useQuery`. `allFacilities` forwards it to every page. Retry on the main and contribution errors. |
| `frontend/src/pages/catalog/TableView.tsx` | Pass `signal`. Draft `start`/`end` state plus "Apply dates". Retry on the preview error. |
| `frontend/src/pages/catalog/Choices.tsx` | Pass `signal`. Load only after first focus (`enabled: opened`). Retry on choice errors. |
| `frontend/src/test/fetchStub.ts` | Respect and record `init.signal`, so tests can assert cancellation. |
| `frontend/src/pages/qa01.test.tsx` | New. The R1–R6 checks. |
| `frontend/tests/e2e/data.spec.ts` | Add the three-rapid-clicks Playwright regression. |

## Rules

- The retry policy applies only in production setup (`main.tsx`). Test clients keep `retry: false` unless a test opts in.
- The Apply button commits the draft into `filters`. React Query hashes equal filter values to the same key, so an Apply with no change sends nothing.
- The lazy Facility query uses `enabled: opened`. The first focus of the search input or the Facility select sets `opened`.
- A cancellation stays an `AbortError`. `request()` already rethrows it, and React Query ignores it.

## Failure result

A failed fetch with no HTTP response and no `AbortError` becomes `ApiError status 0`, as today. The retry rule does not retry it automatically; the user gets the Retry button.
