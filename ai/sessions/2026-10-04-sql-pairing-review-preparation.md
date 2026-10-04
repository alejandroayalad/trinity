# SQL pair-programming gate — review preparation

Date: 2026-10-04 (America/Merida)
Branch: `feat/catalog-permissions`; starting HEAD `fde733b`.
Status: Stop before core-validator implementation for human case review.

## Objective and authority

[ME] Alayala authorized the first implementation gate as human/AI pair programming: inspect the approved design, identify exact SQLGlot AST checks and DataFusion APIs, prepare only minimum tests/dependencies, then stop before core validation. He will review cases and implement or pair-program the validator. Only after that validator works may AI add repetitive DataFusion compatibility infrastructure; he will review failures and the security-sensitive execution path. The HTTP endpoint is explicitly excluded. Incremental commits are requested; no push is authorized.

[YOU] AI followed this narrower boundary, updated current task/design guidance and prepared the [pairing review](../../sdd/single-table-sql/pairing-gate.md). No validator skeleton, callable allow/deny function, normalization/rewrite implementation, production query package, DataFusion execution harness or endpoint was added. This records observed participation only; it does not claim alayala has reviewed or understood the cases yet.

## Input, flow and output

Input: approved grammar plus bundled synthetic SQL examples. Flow: inspect installed libraries and parse bounded examples → record tree/token distinctions → add plain JSON proposal data and unittest characterizations → present cases for human review. Output: 81 proposed cases (25 allow, 52 reject, four later engine/type review) and seven parser-characterization tests.

Failure example: an implementation authorizes all Coalesce nodes. SQLGlot also produces Coalesce for NVL/IFNULL, which the approved function list excludes. The reference/tests expose that normalization fact; they do not implement the correction. Similar tests expose DATE/CAST and omitted/explicit null-order equivalence. These are preparation observations, not findings against an existing validator.

## Inspection evidence

Read repository instructions, CONTRIBUTING, current project/decision context, approved SQL design/specification/tasks and latest session. Inspected existing unittest style and current Git status/worktrees before any edits. The index was empty. Existing catalog and Docker changes were present on the branch and retained.

Installed versions observed: SQLGlot 30.21.0, DataFusion 54.0.0 and PyArrow 25.0.1, matching project pins. Used the existing backend virtual environment and unittest; no dependency or lockfile change/install. The signature probe imports DataFusion to inspect classes/methods but never constructs SessionContext, plans a query, executes SQL or opens Parquet.

SQLGlot inspection ran parse/tokenize on synthetic examples only. Recorded Select/from_, populated argument restrictions, Table wrapping ReadParquet, Join from comma FROM, In.query, Case/If, function argument shapes/default flags, parser-generated Cast and function aliases, numeric literal spelling, comments/hints, and full parse lists including trailing None. Proposed review points map to the exact installed version; they are not a general permission algorithm.

The API inventory includes SessionConfig, SQLOptions deny controls, RuntimeEnvBuilder, SessionContext.sql/register_parquet, DataFrame.schema/limit/execute_stream and RecordBatch.to_pyarrow. Consulted official DataFusion context/DataFrame/configuration documentation. The SQLGlot parser webpage exceeded the tool's page-size limit, so pinned installed source supplied its exact details. References are linked from the review note; no documentation description is represented as runtime compatibility evidence.

## Checks and boundaries

Executed from backend: `.venv/bin/python -m unittest discover -s tests -p 'test_sql_review_scaffold.py' -v`.
Observed: **7 tests passed in 0.009 seconds**, with no skips. They characterize parser behavior. They do not exercise the fixture allow/reject expectations against a validator. The 81 cases remain proposed and await human review.

The scaffold never imports production app/services or executes the rejected SQL. No DataFusion compatibility suite, full application regression, database, container, S3/EIA or retained-account check ran: this gate changes only test data/characterizations and documentation, and the user explicitly reserved later execution work. Input-size/depth/process supervision, table/role authorization, exact numeric semantics and isolation remain unimplemented/unverified.

Documentation checks confirmed all 81 matrix rows match the JSON fixture and all case IDs are unique. Nineteen local links across the four review documents resolve; code fences and whitespace checks passed. Preservation hashes show no unrelated pre-existing file changed, and no production queries package exists. `git diff --check` passed. Maintain data evidence — ongoing; synthetic SQL is not a source-data anomaly or publication.

## Incremental Git delivery

First commit: `611bcea`, `docs(sql): record approved one-table query design and tasks`. It records the previously approved SQL SDD and supporting sessions plus only SQL-specific canonical/README/NOTES changes. Selective index patches excluded pre-existing catalog refinements and Docker work; working files were not reset or replaced. Staged-document links were checked against staged files before committing.

Second commit: the review matrix, parser-only scaffold, pairing note, current design/task boundary and this evidence. Its exact file list is reviewed before commit; only this new NOTES section and SQL README row are staged from mixed files. No amend, squash, force operation, push or remote change is part of this task.

## Review checkpoint

Done: approved design inspection, exact AST/API reference, proposed matrix, minimal parser scaffold and focused local commits.
Pending: alayala's review and human/AI implementation of the core validator; later DataFusion infrastructure remains conditional on a working validator.
Blocker: none for review. Token-origin distinctions and future numeric/execution behavior require careful implementation and evidence.

Next: [ME] review A01/B01–B03 for the complete-input rule, then choose the first core check to pair on.
