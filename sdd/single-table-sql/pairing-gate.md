# Pairing gate: review SQL cases before writing the validator

Date: 2026-10-04
Status: The paired whole-input/single-SELECT check is implemented. Full policy, SQL execution and HTTP endpoint remain unimplemented.
Authority: alayala's explicit pair-programming instruction supersedes autonomous implementation of Step 2 in [tasks.md](tasks.md). The approved [specification](spec.md) and [design](design.md) remain the behavior targets.

## Human

### Current paired step — whole input only

Alayala supplied the `validate_single_statement` flow and authorized only this first check. [Implementation evidence](../../ai/sessions/2026-10-04-sql-single-statement-pairing.md) records ten passing focused tests and seven unchanged parser characterizations. A01 passes; B01/B02 and the original B03 (`;;`) fail. The latest single-`;` example passes. Table checks and comparisons 2–5 remain later paired steps.

The strict length check currently rejects A24: SQLGlot emits an extra Semicolon node for a comment after the terminal semicolon. This is a known gap against the approved comment grammar, not a newly accepted restriction. Review its handling before completing the whole-input policy. A passing Select root does not authorize downloads or execution.

### Start with these five comparisons

The matrix is proposed test data for your review. It is not a policy implementation or a record of passed authorization tests.

| Proposed allow | Proposed reject / contrasting behavior | What we need to check |
|---|---|---|
| A01: one SELECT from national_outages | B01/B02: a second statement, even another SELECT | Parse the entire input; do not validate only the first statement. |
| A04: one aliased table | B10/B11: comma FROM or self-join | Count references and inspect all clauses, not just the distinct table-name set. |
| A10: DATE '2025-01-01' | B23: CAST('2025-01-01' AS DATE) | SQLGlot produces the same expression tree; retain the original token form. |
| A17: COALESCE(outage, 0) form | B21/B22: NVL or IFNULL | All normalize to Coalesce; inspect the original function spelling too. |
| A21: ORDER BY outage DESC | A22: explicit DESC NULLS FIRST is also allowed | Their parser trees match; D03 requires omitted null order to become LAST while explicit FIRST remains FIRST. |

Input to this scaffold is bundled synthetic SQL. SQLGlot produces a syntax tree; seven tests check the observed shapes and normalization differences. Output is parser-characterization evidence only. If a library change merges or changes a shape, a characterization failure prompts review. No decision function is called and none of the proposed allow/reject expectations is exercised against a validator yet.

**Your part:** review the cases, then implement or pair-program the core validator. **AI's later part:** only after that validator works, add repetitive DataFusion compatibility fixtures/runners. You review failures and the security-sensitive execution path. The HTTP endpoint remains excluded from this authorization.

### What is ready

The existing environment already has SQLGlot 30.21.0, DataFusion 54.0.0 and PyArrow 25.0.1, matching project pins. The existing unittest runner is sufficient. No package install, dependency/lockfile update, database, Docker, S3 or EIA setup is needed for this gate.

From the repository root, run only the parser characterization checks:

```bash
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_sql_review_scaffold.py' -v
```

The [fixture file](../../backend/tests/fixtures/sql_review_cases.json) contains 25 proposed allow cases, 52 proposed reject cases and four later engine-review cases. The [test scaffold](../../backend/tests/test_sql_review_scaffold.py) deliberately does not implement or import a validator. The separate single-statement check now exists; it is not the full policy. A passing scaffold is not a passing SQL security suite.

## LLM and pairing reference

### AST concepts in the installed SQLGlot version

AST means abstract syntax tree: each object describes one SQL construct, and its children describe its parts. `exp.Select` is a SELECT node. `node.args` holds named children and flags; `expressions` often holds a list. `this` is a node's main child, not necessarily an identifier or string. A `Table` can wrap a file-reading function.

`Expression.walk()` visits descendants; `find_all(exp.Table)` can locate table-shaped references but is not sufficient authorization. `Select.args["from_"]` is the FROM clause in this version. `Identifier.this` preserves the name and `Identifier.quoted` records quoting. `Literal.is_string` distinguishes string from numeric tokens, but a numeric Literal may still use excluded scientific notation.

`arg_types` describes parser arguments and whether they are required; it is not a security allowlist. Likewise `Func.sql_name()` reports a normalized name and can hide the source spelling. Do not treat all Func subclasses, all Cast nodes or all Table nodes as authorized. Position and arguments matter as much as the node class.

The following is an inspection/reference table, not executable policy. Every unlisted construct/argument still needs explicit rejection by the future validator. False flags can be meaningful; do not drop them with a truthiness filter.

| Node / location | Exact checks needed for the approved subset |
|---|---|
| Whole input | `sqlglot.parse(..., read="postgres", error_level=ErrorLevel.IMMEDIATE, max_errors=1, max_nodes=4096)` returns a list. Exactly one nonempty Select is needed, with at most the approved terminal semicolon. Do not discard a trailing None from an extra semicolon. Bound UTF-8 bytes, tokens, recursion/depth and total work separately. |
| Select | Permit only reviewed `expressions`, `from_`, `where`, `group`, `order`, `limit` forms. Inspect/reject populated `with_`, `joins`, `distinct`, `into`, `having`, `qualify`, `windows`, `offset`, `locks`, `hint`, `operation_modifiers` and every other nonselected argument. A Select root alone is insufficient. |
| From / Table | From.this must be the single plain Table, with Table.this an Identifier in the exact canonical table registry. Only its optional TableAlias is permitted. Reject db/catalog, joins, functions, samples, versions, hints and other table modifiers. Visit all descendants for additional physical references. |
| TableAlias / Column | TableAlias.this is one identifier, never a column-renaming list. Column.this is a known source Identifier (or an allowed qualified Star); Column.table must resolve to the one source/alias. Reject db/catalog/join_mark/shadow and unknown or ambiguous names. |
| Identifier / Alias / Star | Preserve exact name/quoted state; reject extra identifier modifiers. Alias.this is an approved expression and alias is a bounded output Identifier. Star must have no except_/replace/rename/ilike modifiers and appear only in approved projection/COUNT positions. Public duplicate labels are allowed; ambiguous ORDER BY references are not. |
| Literal / Boolean / Null / date | Numeric spelling must be an approved finite integer/fixed-point form, not exponent syntax. Boolean.this is a boolean; Null has no children. A typed DATE currently becomes Cast(Literal, DataType(DATE)); validate original DATE-token form, real date value, and no arbitrary casts/parameters/types. |
| Paren / Neg / Add / Sub / Mul / Div | Validate scalar operands recursively and their context. Unary plus is normalized away. Ordinary division in this profile carries `typed=True`, `safe=False`; those are observed parser defaults, not permission for new division variants. |
| EQ / NEQ / GT / GTE / LT / LTE / And / Or / Not | Validate the selected binary/unary operands and predicate placement; reject hidden subqueries or unsupported expressions inside them. Both != and <> normalize to NEQ. |
| Is / Between / In | Is.expression must be Null; IS NOT NULL uses `negate=True` in this release. Between has this/low/high and NOT wraps it; reject symmetric variants. In permits only nonempty literal expressions; reject `query`, `unnest`, `field`, `is_global`. |
| Case / If | Searched Case has no Case.this, a nonempty ifs list and optional default. Each If contains predicate this and result true; no standalone IF function or unreviewed false argument. Simple CASE has Case.this and is excluded. |
| Count / Sum / Avg / Min / Max | Count accepts Star or one scalar expression, no Distinct/filter/window/multiargument modifiers. `big_int=True` is the observed COUNT parser flag; specify the accepted profile rather than reject the default blindly. Sum/Avg/Min/Max each require one operand; Min/Max also have an expressions list that must not add arguments. Reject nested aggregates and illegal clause placement. |
| Round / Coalesce / Nullif | Round.this is numeric expression and optional decimals is a signed integer literal (Neg(Literal) for negative scale); reject truncate/casts_non_integer_decimals modifiers. Coalesce uses this plus expressions (at least two total), but original spelling must be COALESCE. Nullif has this/expression. Verify original spelling for all eight selected functions and reject extra modifier flags. |
| Group | Only source-column references in expressions; reject grouping_sets/cube/rollup/totals/all. No positional ordinals or output-alias interpretation. |
| Order / Ordered | Order.expressions contain approved source columns or unique output aliases. Ordered.this identifies that expression, desc and nulls_first encode order. Retain explicit versus omitted NULLS syntax separately; no with_fill or positional ordinal. D03 defaults are application rules, not PostgreSQL defaults. |
| Limit | Only expression containing a nonnegative integer literal; reject offset/limit_options/extra expressions. Do not accept a Neg, computed expression, parameter, FETCH or percent/ties form. |

Token checks are supplements to structural checks, not substring blacklists. A25 contains SQL-looking text inside a string and remains allowed. Source-spelling checks must locate the actual construct, not reject a quoted alias or string merely because it contains CAST, NVL or SELECT. Review token offsets/comments and node meta together before choosing the implementation. All normalization must preserve the bound table, selected expressions and explicit ordering; user-supplied private-looking aliases must never activate a trusted internal mode.

### Confirmed parser behavior that changes the implementation approach

These are small local parsing observations, not code-review defect findings or engine execution evidence:

| Cases | Observed in SQLGlot 30.21.0 / postgres | Implication for the future validator |
|---|---|---|
| A10 / B23 | Their projection Cast nodes compare equal. DATE versus CAST is visible in tokens. | Do not authorize Cast solely by its target DATE type. |
| A21 / A22 | Both Ordered nodes have desc=True, nulls_first=True and compare equal. | Preserve whether NULLS FIRST was written before applying D03’s omitted-order default. |
| A17 / B21 / B22 | All first projections are Coalesce; function node meta start/end identify the original spelling in these examples. | Normalized function class/name alone would admit unapproved aliases. Verify source-span behavior before relying on it generally. |
| B10 / B17 | Comma FROM has Select.joins; read_parquet is Table.this=ReadParquet. | Do not trust only From.this being Table or a single known distinct table-name set. |
| B03 / B38 / B44 | Extra semicolon produces trailing None; 1e2 stays Literal; hint text is in Select.comments. | Inspect whole parse/token/comment information as well as node classes. |

### DataFusion APIs for the later compatibility harness

Only signatures/source were inspected; no SessionContext was instantiated, no query planned/executed, and no Parquet created by this gate. These APIs exist in the installed 54.0.0 package:

| API | Later use / review boundary |
|---|---|
| SessionConfig.set(key, value), with_information_schema(False) | Explicit parser/config settings and no information schema. Candidate keys are `datafusion.sql_parser.dialect`, `datafusion.sql_parser.parse_float_as_decimal`, `datafusion.sql_parser.enable_ident_normalization`. Exact pinned-value acceptance/ANSI behavior must be tested later, not assumed from documentation. |
| SQLOptions.with_allow_ddl(False), with_allow_dml(False), with_allow_statements(False) | Independent engine restrictions supplied to every `SessionContext.sql` call. These controls do not implement the one-table/function policy. |
| RuntimeEnvBuilder.with_greedy_memory_pool(bytes), with_disk_manager_disabled() | Engine allocation/spill controls from the design; neither proves a container memory ceiling. |
| SessionContext(config, runtime), register_parquet(name, path, schema=...) | Fresh context and one trusted temporary Parquet table with canonical Arrow schema, after reviewed validation. No external stores, arbitrary paths or UDFs. |
| SessionContext.sql(query, options=...) | Accept only the approved operation; leave param_values/named_params unused. Never send the rejected matrix here to “see if it works.” You review this execution entrypoint. |
| DataFrame.schema(), limit(1001), execute_stream() | Check result shape, cap final output after the user's limit, and stream batches. This must not cap aggregate input. |
| RecordBatchStream.__iter__/__next__, RecordBatch.to_pyarrow() | Read bounded Arrow batches while preserving exact decimals and ordered columns. Avoid dict conversion that drops duplicate labels or float conversion of measurements. |

Official references: [DataFusion context](https://datafusion.apache.org/python/autoapi/datafusion/context/index.html), [DataFrame](https://datafusion.apache.org/python/autoapi/datafusion/dataframe/index.html), and [configuration](https://datafusion.apache.org/user-guide/configs.html). Installed source and signature inspection establish the APIs above; they do not establish configured behavior. The SQLGlot parser documentation fetch exceeded the web tool's size limit, so the pinned installed parser/expressions/tokenizer were used for the exact AST observations.

### Proposed matrix

Every row below exists verbatim in the JSON fixture. Allow/reject expectations derive from the approved grammar but remain proposed test cases until you review them. Engine-review rows identify later type/numeric questions; they are not claimed passing cases. The scaffold asserts only seven parser characterizations.

#### Allowed SQL — proposed

| ID | SQL | Expected check |
|---|---|---|
| A01 | `SELECT period, outage FROM national_outages ORDER BY period LIMIT 10` | Basic national selection, ordering and limit. |
| A02 | `SELECT facility, "facilityName", outage FROM facility_outages WHERE facility = '00566'` | Canonical facility columns; source IDs remain strings. |
| A03 | `SELECT facility, generator, outage FROM generator_outages WHERE facility = '46' AND generator = '1'` | Generator table; exact facility/generator literals. |
| A04 | `SELECT n.* FROM national_outages AS n` | One table alias and qualified star. |
| A05 | `SELECT * FROM national_outages` | Plain star expands canonical column order. |
| A06 | `SELECT outage FROM national_outages WHERE outage >= 1 AND outage <= 2 OR NOT (outage = 0) AND outage <> capacity AND outage != -1` | Comparison and boolean tree; also test each operator independently later. |
| A07 | `SELECT outage FROM national_outages WHERE outage BETWEEN 1 AND 2 OR outage NOT BETWEEN 3 AND 4` | Between and Not(Between). |
| A08 | `SELECT facility FROM facility_outages WHERE facility IN ('46', '566') AND facility NOT IN ('371')` | Literal-list IN; no nested SELECT. |
| A09 | `SELECT percentOutage FROM national_outages WHERE percentOutage IS NULL OR percentOutage IS NOT NULL` | Is(Null), including the negate flag. |
| A10 | `SELECT DATE '2025-01-01' FROM national_outages` | Typed DATE literal; must remain distinct from arbitrary CAST. |
| A11 | `SELECT +(outage + 1) - (-capacity * 2) / 3 FROM national_outages` | Scalar arithmetic; unary plus may disappear in the tree. |
| A12 | `SELECT CASE WHEN outage > 0 THEN outage ELSE 0 END FROM national_outages` | Searched CASE; If nodes only as its arms. |
| A13 | `SELECT CASE WHEN outage < 1 THEN NULL END FROM national_outages` | Searched CASE without ELSE; null output. |
| A14 | `SELECT facility, COUNT(*), SUM(outage), AVG(outage), MIN(outage), MAX(outage) FROM facility_outages GROUP BY facility` | All five selected aggregates; grouping by source column. |
| A15 | `SELECT COUNT(percentOutage) FROM national_outages` | COUNT(expression) keeps SQL null semantics. |
| A16 | `SELECT ROUND(outage), ROUND(outage, 2), ROUND(outage, -1) FROM national_outages` | ROUND argument shapes; exact rounding compatibility is later. |
| A17 | `SELECT COALESCE(percentOutage, 0), NULLIF(capacity, 0) FROM national_outages` | Selected scalar/null functions. |
| A18 | `SELECT ROUND(SUM(outage), 2) AS total FROM national_outages ORDER BY total` | Scalar function wrapping aggregate output; unique output alias. |
| A19 | `SELECT "percentOutage", "outage" AS "value" FROM "national_outages"` | Quoted identifiers preserve exact canonical spelling. |
| A20 | `SELECT outage AS value, capacity AS value FROM national_outages` | Duplicate public output labels are allowed when not ambiguously referenced. |
| A21 | `SELECT outage FROM national_outages ORDER BY outage DESC` | Omitted null order must become NULLS LAST under D03. |
| A22 | `SELECT outage FROM national_outages ORDER BY outage DESC NULLS FIRST` | Explicit NULLS FIRST must survive; AST resembles omitted null order. |
| A23 | `SELECT outage FROM national_outages ORDER BY outage ASC NULLS LAST LIMIT 0` | Explicit null order and zero limit. |
| A24 | `/* ordinary comment */ SELECT outage FROM national_outages; -- done` | Ordinary comments and one terminal semicolon. |
| A25 | `SELECT 'DROP TABLE local_users; -- text' AS note, TRUE, FALSE, NULL, 1.25 FROM national_outages LIMIT 1` | SQL-looking text is a string literal, not another statement. |

#### Rejected SQL — proposed

| ID | SQL | Expected check |
|---|---|---|
| B01 | `SELECT outage FROM national_outages; DELETE FROM national_outages` | All statements must be inspected; trailing write. |
| B02 | `SELECT outage FROM national_outages; SELECT capacity FROM national_outages` | Two read-only statements are still outside v1. |
| B03 | `SELECT outage FROM national_outages;;` | Extra empty statement must not be discarded silently. |
| B04 | `SELECT 1` | Exactly one physical analytical table is required. |
| B05 | `SELECT * FROM local_users` | Application-state table is unavailable. |
| B06 | `SELECT * FROM unpublished_candidate` | An unpublished/unknown name is not analytical authority. |
| B07 | `SELECT * FROM national` | Internal registry key is not a public SQL table. |
| B08 | `SELECT * FROM public.national_outages` | Schema qualification is excluded. |
| B09 | `SELECT * FROM national_outages n JOIN facility_outages f ON n.period = f.period` | JOIN is excluded even for permitted names. |
| B10 | `SELECT * FROM national_outages, facility_outages` | Comma FROM becomes a Join node. |
| B11 | `SELECT * FROM national_outages a JOIN national_outages b ON a.period = b.period` | Self-join is still a join. |
| B12 | `WITH n AS (SELECT * FROM national_outages) SELECT * FROM n` | CTE is excluded. |
| B13 | `SELECT * FROM (SELECT * FROM national_outages) n` | FROM subquery is excluded. |
| B14 | `SELECT * FROM national_outages WHERE period IN (SELECT period FROM facility_outages)` | In.query is not an IN literal list. |
| B15 | `SELECT (SELECT MAX(outage) FROM facility_outages) FROM national_outages` | Subquery hidden inside projection. |
| B16 | `SELECT outage FROM national_outages ORDER BY (SELECT MAX(outage) FROM facility_outages)` | Subquery hidden inside ORDER BY. |
| B17 | `SELECT * FROM read_parquet('private.parquet')` | Table.this can be a function, not Identifier. |
| B18 | `SELECT * FROM "s3://private.invalid/candidate.parquet"` | External storage URL cannot be a table. |
| B19 | `SELECT custom_fn(outage) FROM national_outages` | Anonymous/custom function is not approved. |
| B20 | `SELECT ABS(outage) FROM national_outages` | Known builtin outside the eight-function list. |
| B21 | `SELECT NVL(outage, 0) FROM national_outages` | Normalizes to Coalesce but the spelling is not selected. |
| B22 | `SELECT IFNULL(outage, 0) FROM national_outages` | Another unapproved spelling normalizing to Coalesce. |
| B23 | `SELECT CAST('2025-01-01' AS DATE) FROM national_outages` | Explicit CAST shares the allowed typed-date tree. |
| B24 | `SELECT '2025-01-01'::DATE FROM national_outages` | PostgreSQL cast spelling is also unapproved. |
| B25 | `SELECT DISTINCT outage FROM national_outages` | SELECT DISTINCT is excluded. |
| B26 | `SELECT COUNT(DISTINCT outage) FROM national_outages` | Distinct modifier inside an otherwise allowed function. |
| B27 | `SELECT SUM(outage) FILTER (WHERE capacity > 0) FROM national_outages` | Aggregate FILTER wrapper is excluded. |
| B28 | `SELECT SUM(outage) OVER () FROM national_outages` | Window expression is excluded. |
| B29 | `SELECT facility, SUM(outage) FROM facility_outages GROUP BY facility HAVING SUM(outage) > 0` | HAVING is excluded. |
| B30 | `SELECT outage FROM national_outages LIMIT 10 OFFSET 1` | OFFSET is excluded. |
| B31 | `SELECT outage FROM national_outages UNION ALL SELECT outage FROM national_outages` | Set operations are excluded. |
| B32 | `SELECT facility FROM facility_outages WHERE facility LIKE '5%'` | LIKE is outside the selected predicates. |
| B33 | `SELECT CASE outage WHEN 0 THEN 1 ELSE 0 END FROM national_outages` | Simple CASE sets Case.this; only searched CASE is selected. |
| B34 | `SELECT outage FROM national_outages ORDER BY 1` | ORDER BY ordinal is excluded. |
| B35 | `SELECT facility, COUNT(*) FROM facility_outages GROUP BY 1` | GROUP BY ordinal is excluded. |
| B36 | `SELECT outage FROM national_outages LIMIT -1` | LIMIT must be a nonnegative integer literal. |
| B37 | `SELECT outage FROM national_outages LIMIT 1 + 1` | Computed LIMIT is excluded. |
| B38 | `SELECT 1e2 FROM national_outages` | Scientific notation remains a Literal; check spelling. |
| B39 | `SELECT outage FROM national_outages WHERE outage > $1` | User parameters are excluded. |
| B40 | `SELECT missing_column FROM national_outages` | Resolve columns against the canonical table schema. |
| B41 | `SELECT outage AS value, capacity AS value FROM national_outages ORDER BY value` | Ambiguous output alias cannot determine ordering. |
| B42 | `SELECT * FROM national_outages AS n(renamed)` | TableAlias.columns is not allowed. |
| B43 | `SELECT * FROM national_outages FOR UPDATE` | Lock modifier is excluded. |
| B44 | `SELECT /*+ hint */ outage FROM national_outages` | Hint text can survive only as comments in this dialect. |
| B45 | `SELECT DATE '2025-02-30' FROM national_outages` | Parser acceptance does not prove a real calendar date. |
| B46 | `SELECT COALESCE(outage) FROM national_outages` | Coalesce requires at least two scalar arguments. |
| B47 | `SELECT MIN(outage, capacity) FROM national_outages` | Selected MIN is single-argument aggregate, not multiargument form. |
| B48 | `SELECT ROUND(outage, capacity) FROM national_outages` | ROUND scale must be an integer literal. |
| B49 | `SELECT SUM(AVG(outage)) FROM national_outages` | Nested aggregates are excluded. |
| B50 | `DROP TABLE national_outages` | DDL is not a SELECT. |
| B51 | `SET timezone = 'UTC'` | Session statements are excluded. |
| B52 | `EXPLAIN SELECT outage FROM national_outages` | EXPLAIN is outside the grammar even if read-only. |

#### Later engine/type review — not executed

| ID | SQL | Expected check |
|---|---|---|
| E01 | `SELECT outage / 0 FROM national_outages` | Permitted syntax; reachable zero division must fail safely without partial output. |
| E02 | `SELECT AVG(outage), ROUND(outage, -1) FROM national_outages GROUP BY outage` | Inspect exact output type, scale and rounding using synthetic decimals after validator review. |
| E03 | `SELECT SUM(facilityName) FROM facility_outages` | Grammar uses approved names; numeric type requirement must fail safely. Review static versus engine error boundary. |
| E04 | `SELECT period, SUM(outage) FROM national_outages` | Invalid grouping must fail safely; not a reason to permit hidden subqueries or rewrite the user query. |

### Boundary cases to expand after review

The core matrix is a starting review set, not exhaustive security acceptance. Add parameterized cases for UTF-8 text bounds (16,384/16,385 bytes), token/node/depth limits, quoted and mixed-case identifiers, invalid function arities, empty IN, table/version/qualified-function modifiers, each comparison operator, and nested unsupported syntax in every allowed clause. Multi-statement parsing must cover comment-only/leading/trailing semicolons and semicolons inside strings. Source-token checks must not confuse aliases, strings or ordinary comments with active SQL.

Keep Viewer denial, no-publication ordering, forbidden-download guards, role changes and HTTP body/error handling in their later layers. SQL policy cannot establish the caller's trusted role on its own. No HTTP implementation or resource-isolation acceptance is part of this gate.

One scope detail to resolve during review: A19 excludes URLs/external readers, while scalar strings are allowed. The external table/reader cases are unambiguous. Do not silently decide how an ordinary URL-valued scalar string is classified; review it before adding a general URL detector. Likewise settle known-type/grouping error classification using E03/E04 without widening syntax.

### Stop point

Done: first paired single-statement check; ten focused tests and seven parser characterizations passed.
Pending: A24 comment handling review, then paired table/token checks; full policy and engine acceptance remain unimplemented.
Blocker: the strict count check rejects the approved A24 form.

Next: [ME] review the A24 parser result before expanding this check.
