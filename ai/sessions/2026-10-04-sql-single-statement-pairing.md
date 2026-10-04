# SQL pairing — whole-input single-statement check

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`; starting HEAD `55a046e`.
Status: bounded implementation complete; stop for review, full policy incomplete.

## Objective and contributions

[ME] Alayala supplied the function signature and parse/count/nonempty/Select flow. He authorized only the whole-input/single-statement check, with A01 allowed and B01/B02 rejected. His latest B03 text contains one terminal semicolon; the existing B03 fixture contains two. He also restated the later physical-table, typed-date, function-spelling and null-order comparisons. These remain future paired checks; this record does not claim human understanding or approval of their implementation.

[YOU] Read current instructions, CONTRIBUTING, README, PRODUCT, A19/D01, SQL design and latest pairing session; inspected package/test conventions and dirty status. Added only the minimal query/runtime package, `validate_single_statement`, local `SQLValidationError`, focused tests and updated review status. No endpoint, DataFusion harness, table/column/function policy, SQL rewrite, role/UI work or dependency change.

Input → flow → output: SQL string → SQLGlot full parse with the existing postgres/IMMEDIATE/max_errors=1/max_nodes=4096 profile → require exactly one nonempty Select root → return that tree. ParseError/TokenError become a fixed SQLValidationError with the source exception suppressed in formatted tracebacks. This is not complete resource supervision or safe SQL authorization. Unsupported Select clauses and even application-state table names can pass this first check; nothing calls it to download or execute data.

Failure example: B01 parses to Select plus Delete. The list has two entries, so validation raises before returning a tree. B02 behaves the same with two Select roots. The original B03 keeps the trailing None from `;;` and fails. One terminal `;` passes, preserving the approved optional terminator rule.

## Observed gap and stop point

A24 is approved ordinary-comment syntax, but the pinned SQLGlot 30.21.0 parser returns Select plus Semicolon when a comment follows the terminal semicolon. The user's strict list-length flow rejects it. A focused characterization records that current limitation without redefining the approved grammar. No generic filtering of None/Semicolon nodes was introduced: the original B03 must continue to fail. Token-aware handling needs paired review before whole-input acceptance is complete.

Semicolons inside strings/comments before the terminal boundary do not become extra statements. Empty/comment-only input, non-Select roots, malformed syntax and unterminated strings fail. Tests show that tableless SELECT, forbidden table names, joins and custom functions still pass this limited root/count check, so nobody mistakes it for the complete policy.

Reference: [official SQLGlot parse documentation](https://sqlglot.com/sqlglot/) describes a list of parsed trees. Exact edge behavior above was measured locally in the pinned package; current web documentation does not replace installed-version evidence.

## Checks

From repository root:

- `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_single_statement.py' -v`: 10 tests passed in 0.006 seconds, no skips.
- `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_review_scaffold.py' -v`: 7 tests passed in 0.004 seconds, no skips.

These are bounded synthetic parser/unit checks. Full application regression, DB, Docker, live data, DataFusion execution, roles/UI and full SQL security acceptance were not run. No existing application entrypoint imports this new module. Maintain data evidence — ongoing; no new source-data finding arose.

Delivery uses one incremental local commit for this check and its evidence, under the existing commit authorization. Selective README/NOTES index patches exclude unrelated catalog and Docker work. The focused diff was reviewed, all 154 staged local links resolve, and preservation hashes confirm no unrelated pre-existing file changed. `git diff --cached --check` passed. No push or remote change.

## Checkpoint

Done: supplied single-statement flow implemented; 17 focused/parser checks passed.
Pending: review A24 comment handling, then pair on comparisons 2–5; full validator must work before DataFusion infrastructure.
Blocker: A24 prevents claiming complete approved whole-input behavior.

Next: [ME] inspect the A24 parse result and review how to distinguish its comment-only node from the forbidden extra semicolon.
