# Shared EIA client and one-page fetchers

Date: October 3, 2026. Review branch: build/minimum-python-project, PR #4.

## Objective and contributions

[ME] Alayala requested one shared EIAClient using HTTPX and environment authentication, with one valid response page per route method.
[YOU] AI inspected A9's routes and extraction rules, the historical facility-total evidence, A15's connector boundary, the existing configuration loader and official EIA API documentation. AI authored the client, tests and usage instructions. Human review and the live gate remain pending.

## Behavior and boundaries

EIAClient owns one asynchronous HTTPX client across national, facility and generator requests. Each method sends one HTTPS request using the EIA_API_KEY loaded at construction, a caller-supplied date window, daily frequency, all three measurements and every key field sorted ascending. Page size is 1–5,000; offset is nonnegative. Redirects are rejected. Per-I/O timeout is 30 seconds, with 10 seconds for connecting; an overall extraction deadline remains future work.

The return is an EIAResponsePage with sanitized source rows/metadata, advertised total, API version and warnings. Validation covers response envelope, daily frequency, basic required field types, nonblank IDs, strict calendar dates in the requested window, units and page size. It does not normalize decimal measurements, establish source completeness, validate duplicate keys or reconcile grains. Empty pages are valid. A5's misleading facility total is preserved rather than used as a completion signal.

HTTP failures, JSON/API errors, timeouts and transport failures become safe errors. Echoed request credentials are removed from returns. HTTPX's INFO request-URL logging is filtered to mask api_key values; logging is not disabled. The filter contains no credential and remains installed to protect concurrent client instances. Client cleanup closes its pool. No automatic pagination or retries were added in this slice.

## Verification

`uv run --locked python -m unittest discover -s tests -v` passed 18 tests on Python 3.14.8. Twelve client tests use synthetic responses with HTTPX MockTransport. They check all route paths, authentication/parameters/key sorting, one request per call, response validation, leading-zero IDs, preserved measurement strings, empty pages, facility totals, errors, redirects, timeouts, secret redaction, missing credentials and pool cleanup. The existing Starlette/HTTPX test-client deprecation warning remains.

`tests/live_eia.py` is an explicit live gate for one nonempty page from each route on October 1, 2026. It was not executed: a presence-only check confirmed EIA_API_KEY is absent in this environment. No private vault note was read, no real credential was printed, and no live EIA request was made. Mocked test success is not live API verification. Findings remain unchanged because no source data was fetched.

## Sources and handoff

Repository: docs/schema.md sections 2 and 4; FINDINGS.md; the October 2 Palisades/pagination/metadata session; A15 backend layout.
Official source: https://www.eia.gov/opendata/documentation.php — API keys in query parameters, data column arrays, offsets/lengths, key sorting, string values, error bodies and echoed request credentials. This documentation review is not proof of a live request.

Done: shared client, three one-page methods, offline checks and live-check command.
Pending: human review, live gate, pagination, bounded retries and retrieval records.
Blocker: no EIA key configured for the live gate.

Next: run the live gate locally with the environment key, then add full pagination under A9.
