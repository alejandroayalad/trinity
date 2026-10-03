# EIA pagination

Date: October 3, 2026. Branch: build/minimum-python-project; PR #4.

## Objective and contributions

[ME] Alayala requested pagination until no more pages exist, combined records per route and checks of fetched page/record counts against available response metadata.
[YOU] AI implemented and tested pagination in the shared client and updated documentation and the explicit live gate. Human review remains pending.

## Behavior and contract

A9 requires offset zero, ascending daily-key sorting, pages of at most 5,000 rows, actual-count offset advances and an empty probe after a short page. The new fetch_national, fetch_facility and fetch_generator methods follow those rules and reuse the same HTTPX pool. They retain the fixed caller-supplied date window. Neither a short page nor reaching the advertised total is a stop condition.

EIACollection returns combined rows, sanitized pages, actual page and row counters, advertised total and a total_matches comparison. page_count includes the terminal empty response; data_page_count excludes it. EIA documents a record total, not a separate page count. For national/generator, minimum_data_pages derives ceiling(total/page_size) as a lower bound; short intermediate pages can increase the actual count. No value is invented when the total is absent, and no bound is derived from the unreliable facility total.

Changing supplied totals fail every route. Stable national/generator totals must match the fetched record count. Facility mismatches are preserved without failing collection, following A5 and FINDINGS AN-03. Totals present on only some pages are checked where supplied. Missing totals do not become zero. Duplicate keys within or across pages fail, including repeated pages whose measurement values changed. HTTP/API failures and exhausted bounds never return a partial success.

Implementation bounds are max_pages=1000 including the empty probe and timeout_seconds=300 for one route collection. They are configurable, finite defaults chosen for this implementation, not measured EIA performance or analytical-query policy. Async deadline cancellation stops an in-flight await; explicit deadline checks also cover completed page processing. Limit errors use safe codes.

## Verification

The full offline unittest suite passed: 32 tests, including 14 pagination tests, on Python 3.14.8. Synthetic HTTPX transports cover all routes, exact page multiples, nonterminal short pages, empty routes, absent/partially supplied totals, unreliable facility totals, national/generator mismatches, changing totals on the terminal probe, duplicate/repeated/overlapping keys, mid-scan HTTP/API failure, request budget exhaustion, deadline cancellation and invalid bounds. The existing Starlette/HTTPX warning remains.

The opt-in live test now also fetches all three routes for October 1, 2026 with page_size=50, max_pages=25 and a 120-second per-route deadline. It checks combined counts, terminal empty pages and reliable totals. Syntax was checked, but the live test was not run because no EIA_API_KEY is configured. No new EIA data was fetched; FINDINGS remains unchanged.

Done: bounded pagination, combined records, available-metadata comparisons and offline checks.
Pending: human review, live gate, bounded retries, persistent retrieval records and full data/Parquet validation.
Blocker: live verification still needs the locally configured environment key.

Next: add bounded retries and sanitized retrieval records, preserving the same date window and pagination deadline.
