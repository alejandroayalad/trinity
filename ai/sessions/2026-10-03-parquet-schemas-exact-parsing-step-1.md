# Parquet preparation — Step 1 schemas and exact parsing

Date: 2026-10-03 (America/Merida)
Branch: `feat/parquet-preparation`
Mode: bounded implementation; stop for human diff review before Step 2.

## Objective and contributions

[ME] Alayala requested exact preservation of insignificant trailing-zero decimals, D06 not-applicable handling for absent source percentage/zero capacity with completed evaluation, and durable retention of failed validation/diagnostic evidence without readiness. He requested minimal design, tasks derived from the five existing steps, and implementation of Step 1 only with offline/regression tests. No storage, command integration, publication or unrelated refactoring is authorized for Step 1.

[YOU] AI preserved existing uncommitted proposal/spec/design/README/NOTES work and inspected the canonical schema, A15 layout, source client and test conventions. Added [tasks.md](../../sdd/parquet-preparation/tasks.md), clarified the design/specification and canonical diagnostic guidance, then implemented only schemas and pure row parsing. A9/A13/A15/A17 remain the existing decisions; the clarifications do not waive validation or publication rules. No separate worktree or agent was used; the authentication worktree was left unchanged.

## Implementation and limits

- `contracts/datasets.py` defines the three Arrow schemas, names and daily keys; `contracts/__init__.py` has no infrastructure setup.
- `connector/normalize.py` parses sanitized source rows without I/O or mutation. It returns date/string/Decimal/null values plus D01/D02 observation codes. Unknown source fields and original decimal text remain in caller-owned sanitized evidence on success and failure.
- Decimal fit checks use text lengths, not rounding arithmetic. `Decimal(original_text)` preserves trailing zeros even under low context precision; exact scale-six Arrow conversion is checked. Invalid calendars, blank/numeric identifiers, invalid decimal forms, nonzero excess scale, overflow, negative capacity, invalid optional types and unit mismatches fail safely.
- The extraction client/pipeline/command are unchanged. Window/coverage checks, Parquet writes, manifests, full diagnostics, durable failed-check journals, storage and publication are not implemented here. D06 and durability clarifications are requirements for later tasks, not claimed runtime behavior.

Authorship correction: AI-produced code and synthetic tests are implementation evidence; they are not alayala's manual validation, new EIA observations or full acceptance of the pipeline.

## Verification

Runtime inspected: CPython 3.14.8 and PyArrow 25.0.1 in the existing `backend/.venv`. `uv` was unavailable on the shell PATH and in the checked usual install locations; no package installation or dependency/lockfile edit was needed. Commands below use the repository's unittest workflow directly in that environment, from `backend/`.

| Executed command | Result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -p test_normalize.py -v` | 17 tests passed. Includes exact Decimal tuples, low-precision context traps, Arrow conversion, schema/nullability, lexical preservation and mocked client-to-parser compatibility. |
| `.venv/bin/python -m unittest discover -s tests -v` | 76 tests passed: 17 new plus 59 existing health/configuration/client/pagination/retry/retrieval/command tests. |

Existing Starlette/HTTPX deprecation warning remains; no unrelated dependency fix was attempted. No live EIA request, S3 operation, credential read, Parquet file write or acceptance test for later stages ran. No formatter/linter/type-checker command is configured in the inspected `backend/pyproject.toml`; no new tooling was added. No build, commit, push, PR or remote mutation occurred.

Final checks passed: `git diff --check`, 141 local Markdown links/anchors, balanced fences/whitespace, unique R01–R14/S01–S38 IDs and focused code/document review. Existing production modules, dependency manifest and lockfile remain unchanged; the only new production files are schemas, their package marker and the pure parser. Design remains 88 lines with five implementation steps. The backend diff panel was requested for human review; the app reported it queued.

## Review gate

Done: Step 1 implementation and focused/existing offline checks.
Pending: human diff review. Steps 2–5 remain unchecked and unauthorized.
Blocker: none for review; no later-step work will start automatically.

Next: [ME] review `contracts/datasets.py`, `connector/normalize.py` and `tests/test_normalize.py` in the Step 1 diff.

## Separate documentation delivery

[ME] Alayala requested committing and pushing the preparation documents while leaving only implementation for review. [YOU] AI inspected the index: ten staged Markdown files and four untracked source/test files. The documentation package includes the SDD, contract clarifications, indexes/instructions and authorship/test records. It explicitly labels Step 1 as local, uncommitted work. The four implementation files stay unchanged and outside the commit. This authorizes documentation publication on `feat/parquet-preparation`, not implementation publication, Step 2, a PR or a merge. Earlier no-commit/no-push statements describe the implementation turn before this request.
