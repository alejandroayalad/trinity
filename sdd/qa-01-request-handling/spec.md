# Specification: QA-01 request handling

Date: 2026-10-05
Status: Implemented with this slice.
Basis: [proposal](proposal.md), QA-01 evidence.

## Requirements

| ID | Requirement | Check |
|---|---|---|
| R1 | When a filter, date or preset changes, the previous analytical request is cancelled in the browser. The cancel reaches the server through the existing `supervised_call` disconnect check. | Vitest: two slow answers then a final answer; the first two request signals are aborted and the final data renders. Playwright: three rapid preset clicks show the 30-day result. |
| R2 | A superseded request grants no new request. Rapid clicks in the Dashboard send one request per distinct preset. | Vitest: request count equals the number of presets clicked. |
| R3 | In the Catalog, From and To edits stay in a draft. No request starts until the user clicks "Apply dates". Reset clears the draft. | Vitest: typing sends no preview request; Apply sends one with `start`; Reset clears the fields. |
| R4 | `/facilities` is requested only after the user first focuses the search box or the Facility select. The select keeps a visible fallback for a facility ID from the link. | Vitest: no `/facilities` call before focus; a call after focus. |
| R5 | A query error shows a Retry button when the caller can refetch. A click refetches. A `data_unavailable` error keeps the Waiting screen and adds no Retry. | Vitest: 429 response shows Retry; click sends a second request; `data_unavailable` shows "Nothing to show yet". |
| R6 | A `429 rate_limited` with `Retry-After` ≤ 5 s retries once after that many seconds. A `429` with a longer or missing `Retry-After`, a `503`, and every other code never retry automatically. | Vitest: pure rule cases; a `Retry-After: 1` response recovers to data; a `503` stays at one request. |

## Failure cases

- If the browser does not pass `AbortSignal` to `fetch`, React Query reports the query as successful and the server slot is held. The Vitest abort test covers the pass-through.
- If the lazy Facility control is never opened, a facility link from the Dashboard still shows its ID through the fallback `<option>`. The existing link test covers this.
- If the server sends `Retry-After: 30`, the user must wait for the button. An automatic retry would spend the 30 requests/minute budget.

## Out of scope

- Backend changes. The disconnect path already releases capacity, and security contract L82 forbids releasing a slot on the HTTP end alone.
- SQL Explorer countdown behaviour and command retries.
