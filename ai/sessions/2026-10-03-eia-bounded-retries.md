# Bounded EIA retries

Date: October 3, 2026. Branch: build/minimum-python-project; PR #4.

## Objective and contributions

[ME] Alayala requested retries for temporary failures such as HTTP 429, 500, 502, 503 and 504; at most three attempts; short backoff; no retries for permanent errors; and a simulated exhaustion check.
[YOU] AI implemented the shared request retry loop, updated prior assertions affected by the new behavior, added 11 regression tests and updated the setup/evidence documents. Human review remains pending.

## Behavior and policy

A19 selects three total attempts with one- and three-second waits inside the operation deadline. The EIA client retries exactly the five requested HTTP statuses. Connect/read/write timeouts, read/write errors and remote protocol errors are also treated as temporary. Other HTTP/transport errors fail immediately. This includes HTTP 400/401, redirects, generic ConnectError (which may represent TLS/configuration failure), PoolTimeout and local protocol errors. HTTP-200 API error bodies, malformed JSON and failed data validation are never retried.

The request route and parameters are built once per page and reused across attempts. Only a successful validated page advances pagination. There is no wait after success, a permanent error or the third failed attempt. Raw response bodies and credential-bearing errors are not surfaced.

A new 30-second total deadline covers one page operation, including all attempts, waits and response parsing. It is an implementation bound, separate from analytical-query limits. The earlier per-I/O HTTPX limits remain. The existing route deadline encloses the whole operation and is never reset by a retry. Expiry or caller cancellation interrupts backoff/in-flight work and prevents another attempt. Page counts still represent validated page responses; failed attempts do not count as data pages. Total network attempts remain bounded by three times max_pages and the route deadline.

## Verification

All 43 offline unittest tests passed on Python 3.14.8 with uv 0.12.23. The 11 new retry tests simulate:

- Each selected HTTP status failing exactly three times, with waits of one and three seconds and no final wait.
- Recovery on the third attempt for all three route methods with identical parameters.
- Success on the first attempt without backoff.
- Permanent errors both initially and after a temporary failure.
- Invalid JSON, HTTP-200 API errors and malformed response bodies without retry.
- Bounded selected transport errors and immediate rejection of other transport errors.
- Retry of the same pagination offset without duplicate combined records.
- Page and route deadlines interrupting backoff, plus caller cancellation.

Backoff calls are captured by AsyncMock in count tests; separate deadline/cancellation tests suspend the backoff await so cancellation is exercised. The previous mid-scan failure test now expects three failed attempts after a successful first page. The existing Starlette/HTTPX test-client deprecation warning remains.

No real EIA key was read or printed, no EIA request was made, and no live data finding is claimed. Live verification remains pending the environment key.

Done: bounded retries and simulated exhaustion/permanent-failure checks.
Pending: human review, live gate and persistent sanitized retrieval records.
Blocker: no implementation blocker; live verification still needs an environment key.

Next: record sanitized retrieval details for every attempt, including failed attempts.
