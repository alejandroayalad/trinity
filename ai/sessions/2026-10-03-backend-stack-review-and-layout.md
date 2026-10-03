# Session — Backend stack review and proposed layout

Date: October 3, 2026. Scope: architecture review, author correction, accepted stack additions, and proposed folder layout. No implementation.

## Objective and contributions

[ME] Alayala supplied the Obsidian `Backend Stack.md` for review and asked to settle the stack before continuing with folder architecture. [YOU] AI read that note, the current repository instructions, README, PRODUCT, A4/A6–A12, the data contract, and the previous backend session. The branch is `docs/backend-decisions-architecture`; the checkout was clean before this review. The source note and `First Aproximation.md` remain unchanged.

The note agrees with the accepted Python/FastAPI, Clerk, PostgreSQL/Psycopg, Alembic, and BullMQ/Redis choices. PyArrow, the DataFusion Python binding, SQLGlot, and S3 were initially reviewed as proposals. Their later disposition is recorded below. A technology list does not close the SQL or authentication contracts.

## Author correction and accepted stack

[ME] Alayala corrected AI's storage interpretation: “locally” means application-owned persisted data, independent of fetching observations from an external source during exploration. An internal storage provider used by the application can be S3. Alayala also explicitly accepted PyArrow, DataFusion, and SQLGlot in the context of the proposed Python stack.

[YOU] AI withdrew the disk-only recommendation and R1's requirement-gap conclusion. The quoted word did not justify imposing that constraint on alayala's architecture. This correction belongs in [Engineering Notes](../../NOTES.md#ai-interpretation-error--application-owned-storage), not the data findings. No EIA observation or anomaly changed.

[A13](../../DECISIONS.md#a13--pyarrow-datafusion-python-and-sqlglot-closed) selects the three libraries. [A14](../../DECISIONS.md#a14--application-owned-storage-and-source-independence-closed) records application-owned S3 storage and the clarified source-independence boundary. Dependency versions, concrete S3 deployment, SQL grammar, and runtime tests remain open. The next topic is the folder proposal below; no folder choice is inferred from accepting the stack.

## Initial review recommendation — superseded by author correction

AI initially recommended PyArrow for exact Arrow/Parquet preparation, `datafusion-python` for analytical execution, and SQLGlot for parsing and inspecting SQL under an application-owned allowlist. AI also recommended local disk storage with S3 deferred. Alayala accepted the libraries and corrected the storage interpretation: retain application-owned S3. No dependency was installed.

Separate PyArrow's responsibility from storage: PyArrow writes typed Parquet; the storage location holds versioned files. DataFusion reads only the server-resolved files from one authorized published manifest. Application code enforces immutability and publication; selecting a storage service does not enforce these invariants by itself.

### R1 — Withdrawn storage interpretation

- Severity and scope: withdrawn; this was an AI interpretation error in the architecture review, not a demonstrated application defect.
- Expected: under alayala's clarification, persist extracted Parquet in application-owned storage and query it independently of live EIA requests.
- Observed: `Backend Stack.md` assigns immutable files to “PyArrow + S3” and says DataFusion reads them in S3. That is consistent with the clarified ownership boundary.
- Evidence: the source note, PDF pages 2/4/7 read with `pypdf`, existing A4/A9 separation of refresh from analytical reads, and alayala's explicit correction. The earlier inference from “locally” to machine-local disk was AI's interpretation, not a separate explicit disk-only statement from the brief.
- Failure scenario: AI's recommendation would replace alayala's intended S3 storage and add a disk-only design restriction without his agreement. No runtime failure of the proposed S3 path was demonstrated.
- Recommended correction: retain application-owned S3, record A14, and explain the AI error in Engineering Notes. Do not classify it as an outage-data finding.
- Validation still required: manifest confinement, immutable version handling, source-outage independence, local application startup with configured dependencies, and reader/publication overlap tests. These are implementation checks, not reasons to reopen the withdrawn interpretation.

### SQLGlot assessment — selected parser, security contract still open

The proposed responsibility is reasonable: parse SQL so Trinity can inspect its structure and apply policy. SQLGlot explicitly documents that its parser is lenient; successful parsing is not proof of engine validity. Its scope traversal distinguishes real tables from CTE aliases. These capabilities do not make SQLGlot a security sandbox or prove agreement with DataFusion's parser.

Proposed controls: parse the entire input and require one allowed statement; reject unrecognized syntax and functions; collect/authorize every real table under the supported grammar before registering data; block file/URL access, application-state tables, writes, and engine configuration commands. Any unsupported CTE, join, or subquery must be rejected in full. If supported, inspect its nested sources. Restrict DataFusion capabilities and registered files as an independent layer. SQLGlot dialect selection and engine compatibility require explicit tests with pinned releases; no full-dialect equivalence is assumed.

Example acceptance tests, not executed results:

| Input and actor | Required outcome |
|---|---|
| Analyst: `SELECT period, outage FROM national_outages LIMIT 10` | Allow if it belongs to the selected subset; apply server limits. |
| Analyst: `WITH x AS (SELECT * FROM job_outbox) SELECT * FROM x` | Reject the CTE syntax if unsupported; otherwise resolve `job_outbox` and deny before DataFusion reads any dataset. |
| Viewer: request a generator preview | Deny at the API permission boundary before file registration. |
| Analyst: `SELECT * FROM national_outages; DELETE FROM national_outages` | Reject the entire multi-statement input. |

No SQL policy implementation exists in the inspected repository. No bypass or exploit was reproduced. Inspection of the current Python environment found no importable `sqlglot`, `datafusion`, or `pyarrow`; no packages were installed for this review.

## Flow and provisional folder responsibilities

Read: verify Clerk identity and role → validate the API operation/SQL grammar and table permissions → capture one active publication → resolve its permitted manifest paths → run a restricted DataFusion context → return capped rows with exact decimal serialization.

Refresh: authorized request → PostgreSQL run/outbox transaction → dispatcher → BullMQ worker → EIA extraction, Parquet preparation, and validation → approval when required → publication worker → atomic PostgreSQL publication pointer. A7/A9 remain authoritative.

Earlier AI layout, superseded for discussion by the author's feature-based proposal below; not approved or created:

```text
backend/
  pyproject.toml
  src/trinity/
    main.py       # API entrypoint
    worker.py     # Background worker entrypoint
    api/          # FastAPI routes and request/response models
    auth/         # Clerk verification and shared role policy
    queries/      # Catalog, previews, SQL policy, DataFusion execution
    connector/    # EIA requests, preparation, data validation
    refresh/      # Workers, scheduling, outbox dispatch, publication
    storage/      # Version files and manifest resolution
    state/        # Psycopg repositories and transaction boundaries
  migrations/     # Alembic revisions
  tests/          # Backend, connector, and worker tests
frontend/         # Framework remains undecided
docs/             # Existing canonical schema and architecture records
```

Recommend one importable Python package with API and worker entrypoints sharing the same rules. The connector moves inside that package in this proposal; README's top-level `connector/` was only a proposed responsibility boundary. This avoids two competing copies of the schema/validation code. No generic adapter framework or extra service is implied. Application-owned S3 files and manifest resolution belong to `storage/`; PostgreSQL state and transaction boundaries belong to `state/`. SQL contracts and versions can remain open during the folder discussion but must close before their implementation.

## Sources and checks

Official sources checked: [PyArrow filesystems](https://arrow.apache.org/docs/python/filesystems.html), [DataFusion Python data sources](https://datafusion.apache.org/python/user-guide/data-sources.html), [SQLGlot parser behavior](https://sqlglot.com/sqlglot.html), and [SQLGlot scope traversal](https://github.com/tobymao/sqlglot/blob/main/posts/ast_primer.md). Documentation supports capabilities, not runtime compatibility or complete security.

No EIA request, cloud provisioning, credential inspection, dependency installation, application execution, commit, or push was performed. The PDF and source note were read only. Initial review checks passed before the correction: 23 relative links/anchors, whitespace in both edited documents, `git diff --check`, and byte comparisons against HEAD for DECISIONS, the canonical schema, README, AGENTS, PRODUCT, and FINDINGS. The later correction adds A13/A14 and updates current guidance; the initial preservation result describes the earlier review state.

Correction checks passed: 69 relative links/anchors across the five edited documents, fourteen unique decision headings, whitespace checks, and `git diff --check`. The canonical schema, PRODUCT, FINDINGS, and earlier backend session remain byte-identical to HEAD. Reviewed the decision/notes/guidance diff and the updated session. No runtime checks were run.

## Author folder proposal review

[ME] Alayala proposed feature folders for `auth`, `catalog`, `queries`, `refresh`, `publication`, and `settings`, with `adapters`, `workers`, `connector`, and `contracts`. Query execution has a separate `queries/runtime/main.py` entrypoint, config, SQL policy, DataFusion engine, and limit handling. The API communicates through `queries/client.py` and `contracts/queries.py`. [YOU] AI recommends this layout over the earlier broad `api/`, `storage/`, and `state/` grouping, subject to the responsibility rules below. This is a proposal review, not a new accepted architecture decision or an implementation review.

Retain the author's file names. The only proposed additional file is `workers/recovery.py`, for A9's periodic reconciliation of durable unfinished runs with queue/progress state. Most refinements are changes to ownership and comments, not additional abstractions.

### R2 — Define the authorization handoff to query execution

- Severity and scope: high if omitted in implementation; currently an unresolved contract in the proposed layout, not a proven vulnerability.
- Expected: authorize every referenced table before any analytical file read or registration under A4/A9/A13.
- Observed: `queries/service.py` is described as authorizing datasets, while the SQL parser lives in `queries/runtime/sql_policy.py`. `contracts/queries.py` names the message contract without defining how those responsibilities connect.
- Evidence: the supplied tree's file descriptions and `docs/schema.md`, section 7 read path. The tree does not specify whether the API parses SQL or supplies the runtime an authorized dataset set.
- Failure scenario: an implementation checks only the request's declared dataset in the API, then the runtime executes SQL referencing another table. If the runtime registers broader data without checking the SQL references against the authorized set, the initial check does not protect that second table. This is a conditional failure, not observed behavior.
- Recommended correction: API service authenticates and derives the permitted dataset set, pins the publication once, and sends server-resolved permitted manifest entries plus query/preview input and limits in the internal contract. Runtime policy parses the entire SQL input and authorizes every real reference against that set before engine registration. It registers only the referenced permitted files. The internal channel must accept requests only from the trusted API. No caller-supplied roles, publication paths, or wider table permissions are trusted. Preview uses the same permitted-file boundary. Keep one SQL policy implementation in the runtime; do not duplicate it in the API.
- Validation still required: nested unauthorized references if supported, invalid message/authentication, attempted path or role substitution, Viewer preview denial, and zero file reads before policy rejection.

### R3 — Enforce isolation outside query code as well

- Severity and scope: high if omitted in implementation; proposed process-boundary contract.
- Expected: a query cannot access API/worker secrets or consume unbounded resources; timeout ends the work, not just the HTTP wait.
- Observed: `queries/runtime/config.py` excludes PostgreSQL secrets and `runtime/limits.py` names time/memory/output limits. The process launcher and resource-enforcement mechanism are unspecified.
- Evidence: the supplied tree; Python's subprocess documentation says the default environment is inherited. For `Popen.communicate(timeout=...)`, timeout does not itself kill the child. Thus separate configuration code is not enough to establish the proposed isolation.
- Failure scenario: an API starts the runtime with its default environment and all API secrets remain in that child; or an API returns a timeout while the child continues consuming CPU/memory. Neither behavior has been tested here.
- Recommended correction: assign process lifecycle supervision to `queries/client.py` or its deployment supervisor. Use an explicitly restricted environment, filesystem/network access, and read-only S3 scope; expose only the manifest/files the request is permitted to read. Keep database, Clerk-management, EIA, and write credentials out of the runtime. The runtime must not import API/worker config through package initialization. Enforce external deadlines/termination and process memory bounds as well as DataFusion limits, bounded message input/output, and global query concurrency. A process alone is not a security sandbox. One process per request versus a bounded pool and the OS/container mechanism remain separate choices.
- Validation still required: synthetic secret inheritance checks, killed/hung child cleanup, memory/output exhaustion, cross-request isolation, and denial of unauthorized files/network access. No real credentials should be used in these tests.

### R4 — Give repositories one transaction owner and complete model coverage

- Severity and scope: medium, proposed persistence ownership; no split-transaction defect demonstrated.
- Expected: A7/A9's related records commit together, and every canonical model has an explicit owner.
- Observed: the tree distributes writes among feature repositories and `adapters/outbox.py`. `refresh/repository.py` mentions runs/steps; `publication/repository.py` mentions publications/approvals/pointer. Candidate versions, artifact metadata, and validation-result persistence are not assigned in those comments.
- Evidence: `docs/schema.md`, section 6 names all ten models; section 7 requires atomic run/outbox creation and publication-event/pointer/run-success updates. The proposal's comments do not settle who owns the missing assignments or commits across repositories.
- Failure scenario: refresh repository commits a run, then outbox persistence fails in another transaction; or publication pointer commits before run completion fails. A7/A9's invariant breaks if repositories independently commit. This is a design test case, not a reproduced defect.
- Recommended correction: feature services own transaction scope through `adapters/postgres.py`; repository/outbox functions use the passed connection and do not independently commit. Extend `refresh/repository.py` ownership to `data_versions`, `dataset_artifacts`, and `validation_results`. `publication/service.py` coordinates publication/approval records and any run transition in the same transaction, using the relevant repositories. Keep the current settings ownership. `adapters/outbox.py` persists/claims outbox data; `workers/outbox.py` dispatches it, without duplicating persistence rules. Keep external EIA/S3/Redis operations outside long database transactions.
- Validation still required: transaction rollback at each write boundary, duplicate delivery, stale-fence rejection, and atomic publication failure tests.

### R5 — Validation must cover the final candidate manifest

- Severity and scope: high for publication correctness if omitted; proposed connector responsibility.
- Expected: the exact generated files pass one complete validation attempt before publication; source-row checks alone are insufficient.
- Observed: `connector/validate.py` is described as validating normalized source data, while `connector/parquet.py` generates files and manifest.
- Evidence: A9 and `docs/schema.md`, section 5 require V08 artifact integrity, frozen manifest binding, and sixteen required result rows in one attempt. The tree's validation comment only names the earlier source stage.
- Failure scenario: normalized rows pass, but a written Parquet file is truncated, has the wrong schema, or is omitted from the manifest. Publishing on source checks alone would expose an invalid candidate. No writer or validator exists to reproduce this yet.
- Recommended correction: retain the files and expand the validation responsibility. `pipeline.py` performs early source checks, writes the candidate, freezes the selected manifest, and validates those exact readable files. Persist results through the feature service/repository. `publication/checks.py` checks that complete evidence and publication eligibility; avoid implementing a second divergent set of data-quality rules there.
- Validation still required: corrupt/missing object, wrong file schema, changed manifest digest, incomplete check results, and mixed-attempt rejection.

### R6 — Assign durable recovery to a periodic worker

- Severity and scope: medium, proposed recovery ownership.
- Expected: requested/running/publishing work lost from Redis or abandoned by a worker is recoverable under A9.
- Observed: `workers/outbox.py` dispatches pending records, `workers/scheduler.py` creates scheduled requests, and `refresh/service.py` owns retry rules. No periodic caller for durable recovery is identified in the proposed tree.
- Evidence: `docs/schema.md`, section 7 recovery rules cover the case after Redis acknowledges delivery, when the outbox is already marked delivered. Neither merely dispatching pending outbox records nor creating the next scheduled run covers that case.
- Failure scenario: enqueue is acknowledged, the outbox becomes delivered, then Redis loses the queued job. Pending-outbox dispatch alone would leave the existing run unfinished.
- Recommended correction: add `workers/recovery.py` as a bounded periodic trigger that delegates recovery rules to `refresh/service.py` and publication services where applicable. It reconciles unfinished durable state, expired leases, and dispatch generations; it does not replay terminal or awaiting-approval runs. Do not duplicate the lifecycle rules inside the worker loop.
- Validation still required: Redis-loss recovery after acknowledgment, worker lease expiry, stale-worker fencing, and no replay of completed/awaiting-approval work.

## Proposed layout review evidence

Read-only checks covered current repository status, A9/A13/A14, the lifecycle/model contract, and the author's supplied tree. Official sources: [Python subprocess environment and timeout behavior](https://docs.python.org/3/library/subprocess.html) and [DataFusion runtime/SQL options](https://datafusion.apache.org/python/autoapi/datafusion/context/index.html). No parser, runtime process, queue, or database test ran; these are design obligations and test scenarios, not findings of implemented defects.

Documentation checks passed: 27 relative links/anchors across the two review documents, whitespace checks, and `git diff --check`. The notes diff and detailed review text were inspected. Existing uncommitted stack/correction changes were preserved.

Next: [ME] accept or reject the author's feature-based layout with these responsibility refinements and `workers/recovery.py`.
