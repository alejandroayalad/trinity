# Proposal: QA-01 request handling

Date: 2026-10-05
Status: Implementation authorized by alayala with the request "implement the slice".
Basis: QA-01 (P1) in the QA report, [API contract](../../docs/api-contract.md), [security contract](../../docs/security-contract.md), A19 in [DECISIONS.md](../../DECISIONS.md).

## Human

### Problem

Rapid actions create more analytical requests than the server admits. The server allows two active analytical requests per user and 30 attempts per minute (`reserve_capacity` and `reserve_rate` in `backend/src/trinity/queries/repository.py`). The server answers the excess with `429 rate_limited` and a `Retry-After` header.

Observed in QA-01:
- Three quick Dashboard preset clicks left the selected 30-day preset with "Too many requests".
- The 1-year and 90-day requests were not cancelled. They ran to completion (53 KB and 13.6 KB).
- A Catalog date edit sent a preview request and a `/facilities` request at the same time.
- After a transient failure, clicking the same preset made no new request. `PageError` has no Retry button.

### Outcome

- The last choice wins. Older requests are cancelled in the browser, and the cancel reaches the server.
- Date edits in the Catalog need an Apply action. Typing alone sends nothing.
- A transient failure has a visible Retry.
- Cancelled work releases server capacity.

### Accepted rules

- R1 The browser cancels a superseded request. The server already stops a disconnected query and frees its slot. The backend is unchanged; only the client must pass the cancel signal.
- R2 A `429 rate_limited` whose `Retry-After` is 5 seconds or less retries once, automatically. Every other failure waits for the user. 503 and SQL behaviour do not change.
- R3 `/facilities` loads only when the user opens the Facility control.
- R4 `PageError` shows a Retry button when the caller can refetch.

## LLM

### Evidence

- `request()` in `frontend/src/api/client.ts` accepts `signal`, but `getDashboard`, `getPreview`, `getFacilities` and `getGenerators` in `frontend/src/api/endpoints.ts` never pass one.
- `supervised_call` in `backend/src/trinity/queries/router.py` checks `request.is_disconnected()` every 0.1 s and sets `cancelled`; `QueryExecution.execute` in `queries/client.py` calls `cleanup` in `finally`, which kills the container and releases the reservation. Real HTTP disconnect tests exist.
- `main.tsx` sets `retry: false`. `pages/shared.tsx` `PageError` is a plain `ErrorState`.

A fetch stub is O evidence. The Playwright check against the real API is the R evidence for cancellation.

### Sequence

1. Specification and design (this folder).
2. Implement signal pass-through, retry rule, Apply dates, lazy choices, Retry button.
3. Vitest checks with the fetch stub.
4. Playwright regression against the running API.
