# One-table read-only SQL — design and tasks

Date: 2026-10-04 (America/Merida)
Branch/base: `feat/catalog-permissions`, `fde733b`; no remote refresh.
Status: Corrected specification approved; design/tasks drafted. Implementation remains unstarted.

## Objective and contributions

[ME] Alayala requested “continue with tasks and design” after clarifying that Viewer must have no SQL button or ability to run user-submitted SQL. This approves the corrected specification and authorizes the design/task artifacts. It does not authorize implementation, builds, database migrations or live execution.

[YOU] AI drafted the [Human/LLM design](../../sdd/single-table-sql/design.md) and [task list](../../sdd/single-table-sql/tasks.md). Recorded D01 grammar and D02 rolling rate accounting under A19, D03 presentation under A16, aligned canonical API/security prose and updated SDD status/README/NOTES. Existing decision and session history remains preserved. New design settings are proposed implementation mechanics, not proof of runtime behavior or separately accepted product decisions.

## Source inspection and design findings

Current auth dependencies hold a repeatable-read database transaction through the protected route. The SQL design closes short transactions before parsing/downloads/execution and rechecks identity with the pinned publication snapshot. It preserves existing auth/catalog behavior and separates auth, dependency and analytical deadline error codes.

`data_versions` already stores a frozen manifest digest; the existing writer uses a fixed manifest object within the server-owned version root. The design binds that digest to the publication, downloads and verifies the manifest after policy/admission, and stages all selected table files. It does not invent a client storage selector or implement publication writes.

Concurrent uncommitted API Docker files now exist. They configure the API/database and do not prove query isolation. They were inspected and preserved. The prior proposal's absence evidence refers to its earlier inspection, and its missing query-specific runtime/image remains accurate. A separate query image and narrowly scoped later Compose additions are planned. `docker --version` could not run because Docker is not in the agent PATH; this does not establish that the user has no Docker installation.

The design makes create/start records, conditional ownership, ambiguous daemon outcomes and late-start recovery explicit. Slots remain occupied on uncertain execution/cleanup. Query-only recovery is scoped independently of refresh/BullMQ work. The public endpoint remains the final integration stage after real isolation/termination evidence.

## Read-only technical evidence

Executed `backend/.venv/bin/python` with imports, importlib.metadata and inspect only. Observed installed versions: SQLGlot 30.21.0, DataFusion 54.0.0 and HTTPX 0.28.1. Inspected signatures for SessionContext.sql/register_parquet, SessionConfig, SQLOptions and RuntimeEnvBuilder; source confirms SQLGlot Parser.max_nodes, DataFrame.limit and execute_stream. No SQL statement, engine context/query, Parquet scan, database or network storage operation was executed by this probe. It is not fresh-install or compatibility evidence.

Consulted official [SQLGlot parser documentation](https://sqlglot.com/sqlglot/parser.html), [DataFusion context API](https://datafusion.apache.org/python/autoapi/datafusion/context/index.html), [DataFusion configuration](https://datafusion.apache.org/user-guide/configs.html), [Docker Engine API](https://docs.docker.com/reference/api/engine/), [attach](https://docs.docker.com/reference/cli/docker/container/attach/), [runtime controls](https://docs.docker.com/engine/containers/run/) and [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/). These describe available interfaces, not successful Trinity enforcement. Local installed signatures take precedence for available Python methods; actual configured behavior remains a test gate.

The first implementation gate must resolve exact decimal precision/ROUND behavior, AST/config mapping and accepted fixture compatibility. The plan does not silently substitute floats, relax SQL scope or change pins on failure. Container/socket/subpath/attach compatibility, restricted storage credentials and live published storage remain separate evidence boundaries.

## Preservation and checks

This task changes documentation only. Passed: 275 local Markdown file/anchor targets across the edited/new documents; balanced fences and whitespace; unique sequential T01–T20, R01–R24 and S01–S29; the five-stage structure; approved-status consistency; and `git diff --check`. Reviewed the design lifecycle, task coverage and focused canonical/SDD diff. Previous NOTES and specification-session text remain an unchanged prefix.

Hash comparison confirmed all pre-existing files outside the intended documentation edits remained unchanged except `backend/README.md`, which changed concurrently. A new `ai/sessions/2026-10-04-docker-local-setup.md` also appeared concurrently; this task did not write either file and did not roll them back. Source, tests, dependencies/lockfile, Dockerfile/entrypoint/Compose and FINDINGS remained byte-identical to this task’s baseline. The Docker work is not attributed to the SQL design. Later changes in the shared worktree must be rechecked before implementation.

No implementation, test suite, build, Docker/container operation, migration, retained-account operation, cloud mutation, EIA request, commit, push or PR occurred. Maintain data evidence — ongoing; no source-data observation was produced.

## Review checkpoint

Done: approved specification refinements recorded; design and five bounded stages drafted.
Pending: design/task review and explicit implementation authorization; Step 2 is the first code gate.
Blocker: none for planning completion. Docker was unavailable in the agent PATH and numerical/parser/container compatibility remains unperformed.

Next: [ME] review the design and authorize Step 2 if ready.
