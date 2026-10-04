# SQL pairing — terminal semicolon and comments

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`; starting HEAD `f8bef4a`.
Status: clarified statement boundary implemented; stop before physical-table policy.

## Human and AI contributions

[ME] Alayala clarified exactly one real SELECT with zero or one terminal semicolon. Whitespace/comments may follow that semicolon; another semicolon or statement may not. This resolves the comment-handling review from the [previous session](2026-10-04-sql-single-statement-pairing.md) without changing the approved grammar.

[YOU] Inspected current status, function/tests, contribution rules and SQL design. Probed the installed postgres tokenizer/parser on synthetic SQL. Implemented only this boundary in `validate_single_statement`; the user's physical-table/function/date/order comparisons remain later paired work. No claim of human code review or understanding is made.

Input → flow → output: tokenize the complete string, check that any real semicolon is the sole final token, parse the complete string, handle only a verified terminal comment-only Semicolon node, then apply the existing one/nonempty/Select checks. Comments carried by that terminator are preserved on the Select for later policy checks. None entries are not filtered; no raw string splitting or comment-removal regex is used. Failure example: `SELECT outage FROM national_outages; /* comment */ ;` has two real semicolon tokens and fails before returning a tree.

The full parse still uses the pinned postgres dialect and IMMEDIATE/max_errors=1/max_nodes=4096 settings. Tokenization is performed twice through the existing parse entrypoint; this small step favors preserving that reviewed interface. Parser/resource supervision and all remaining policy restrictions are still pending. No application endpoint imports/calls the function; passing this helper does not authorize downloads or execution.

## Verification

From repository root:

- `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_single_statement.py' -v`: 14 tests passed in 0.011 seconds, no skips.
- `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_review_scaffold.py' -v`: 7 tests passed in 0.005 seconds, no skips.

Regression cases include A24, whitespace/line/block/nested comments, extra delimiters/statements after comments, leading semicolons, semicolons in strings/quoted identifiers/dollar strings, malformed trailing block comments, empty inputs and non-Select roots. A01 still passes; B01/B02 and original B03 still fail. The earlier A24 rejection is historical evidence, superseded by this measured correction.

No dependency changes, full application regression, DataFusion execution, HTTP, DB, Docker or live-source tests were needed or run. Maintain data evidence — ongoing; synthetic SQL creates no new source-data finding. Delivery is one incremental local commit under existing authorization, with unrelated catalog/Docker edits excluded and no remote changes. The staged scope is exactly seven SQL files. All 149 staged local links resolve; preservation hashes show no unrelated pre-existing file changed. The focused diff was reviewed and `git diff --cached --check` passed.

## Checkpoint

Done: optional terminator/comment boundary and 21 focused/parser checks.
Pending: paired physical-table validation and remaining policy; no engine infrastructure until the full validator works.
Blocker: none for this boundary.

Next: [ME] compare the physical references in A04, B10 and B11.
