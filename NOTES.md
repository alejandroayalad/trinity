# Engineering Notes — Trinity

Status: data analysis and documentation, October 2, 2026. Application implementation has not started in this discussion. This is the Engineering Notes document required by Arkham. It must grow with actual code and verification evidence.

## Human and AI contributions

| Contributor | Observed contribution |
|---|---|
| Alayala | Set the product direction, challenged the DuckDB recommendation, selected A1–A4, defined shared initial setup, corrected refresh scope, and chose Obsidian for these drafts. Fetched the EIA data, analyzed it, and wrote the original findings. Reconfirmed A4 after discussing daily data. |
| AI | Read the brief and existing notes, checked official technical documentation during the discussion, explained alternatives, and drafted decisions, session summaries, and these documents. Formatted alayala's findings, added evidence limits, ran separate read-only CSV checks, and wrote the session handoff. |

No application code was written in this discussion. There is no generated-versus-handwritten code inventory yet. Update this section with concrete files or changes once code exists. AI-drafted prose is not evidence that the author wrote code or independently debugged it.

## Concrete AI mistakes and corrections

| Observed mistake | How it was caught and corrected |
|---|---|
| The AI kept explaining DuckDB when alayala wanted alternatives. | Alayala clarified the goal. The discussion compared DataFusion and PostgreSQL. |
| The AI recorded automatic publication but left scheduled refreshes open. | Alayala stated that both scheduled and manual refreshes were intended. A2 was corrected. |
| The setup description did not clearly limit setup to the initial shared account. | Alayala clarified that setup must not repeat for each Admin. A3 records the shared scope. |

These are planning and documentation errors. No AI code error has been observed or corrected yet. Do not invent one to fill the submission.

## Verification and its limits

The brief was read directly from the local PDF. Official DataFusion and PostgreSQL documents were consulted during the architecture comparison. Document changes were reviewed and saved contents were checked.

No application test, security test, integration test, or performance measurement has run for the selected architecture. Real CSV rows have now been checked. The three exports cover 640 days from 2025-01-01 through 2026-10-02. Separate AI checks found no duplicate candidate daily keys and no national-versus-sum differences in capacity or outage across 2,560 comparisons. AI also checked the Millstone percentage example, reused generator IDs, and the September–October capacity change. These checks do not prove API download completeness or all source definitions. The document checks do not establish runtime behavior.

When code exists, record each important check with the input, expected result, observed result, command or procedure, and remaining limits. Include permission rejection, write rejection, safe reruns, publication failure, and real-data reproduction as they are implemented and tested.

## Data-work attribution

Alayala  performed the fetching and data analysis. He wrote the original text in `FINDINGS.md`. AI preserved those points and edited their structure, wording, tables, and evidence labels. AI's separate verification is identified in [FINDINGS.md](FINDINGS.md).

AI did not fetch more data, change analysis scripts, or implement application code during this closing task. Authorship of `fetch_eia.py` and `generate_report.py` was not established here. Do not count these scripts as handwritten or AI-generated without evidence.

The formatting review narrowed two claims: matching totals do not prove EIA's internal aggregation process, and a capacity step does not by itself prove the source's seasonal methodology. The report's reproduction command was recorded but not executed during this task.

## Understanding and session handoff

Explain the relevant flow before code changes. After a meaningful change, ask alayala to explain its purpose, a failure case, and the check that detects that failure. Record his answer only when he gives it. Do not infer retained understanding from accepting a recommendation.

Use one dated record per session in `ai/sessions/`. Keep historical evidence there and the current decision in [DECISIONS.md](DECISIONS.md). No commit, push, or remote mutation was performed by this document task. The final challenge repository requires incremental history without squashing or rewriting it.

## Capacity anomaly follow-up — October 2, 2026

[ME] Alayala selected F5 as an anomaly and requested a new section below the existing findings. [YOU] AI compared the two boundary dates by facility, drafted AN-01, and wrote and executed its read-only reproduction command. All assertions passed: the same 55 facilities, 47 increases, eight unchanged, no decreases, and a +2,436.2 MW change matching the national change exactly. The seasonal explanation remains provisional. No application implementation or new accepted architecture decision resulted.

Evidence and remaining limits: [capacity anomaly session](ai/sessions/2026-10-02-capacity-anomaly-facility-comparison.md) and AN-01 in [FINDINGS.md](FINDINGS.md). Earlier entries describe their original sessions; this follow-up adds current verification without changing their attribution.

## Palisades and API evidence — October 2, 2026

[ME] Alayala approved Palisades as AN-02 and requested further anomaly, pagination, and metadata investigation. [YOU] AI checked the two-year exports, consulted EIA/NRC sources, made nine bounded API requests, saved credential-free response evidence, and drafted AN-02 and the API explanation. The exact local reproduction code passed. Alayala then selected the facility API count mismatch as AN-03 instead of Callaway. [YOU] AI added the plain-language entry and rechecked five saved-response counts; all passed without new API calls. See the [supporting session](ai/sessions/2026-10-02-palisades-pagination-and-metadata.md). No application code, accepted architecture decision, or publication validation rule changed.

## Validation rule correction — October 2, 2026

[ME] Alayala rejected a user-facing warning when the counts and required validation checks pass. [YOU] AI recorded A5 in DECISIONS.md and aligned AN-03 with it. Passed versions are ready for the publication mode from A3; failed or unfinished validation keeps them unpublished. This is a selected rule, not runtime evidence. See the [validation decision session](ai/sessions/2026-10-02-validation-publication-rule.md).

## Ongoing anomaly workflow — October 2, 2026

[ME] Alayala requested that data evidence remain ongoing, with a process for recording new potential anomalies. Alayala added the workflow to AGENTS.md and linked it from FINDINGS.md. Candidates are recorded with evidence and status; verification and author selection precede promotion to the AN list. Three anomalies are a minimum, not a cap. See the [workflow session](ai/sessions/2026-10-02-ongoing-anomaly-workflow.md).

## Background refresh and reliable dispatch — October 2, 2026

[ME] Alayala selected background workers for the entire refresh pipeline, required bounded concurrency, chose PostgreSQL + Redis + BullMQ, and accepted `job_outbox`. He explicitly requested that these choices be recorded in DECISIONS.md. The exact schema, concurrency values, language, and worker layout were not selected.

[YOU] AI checked official BullMQ documentation and the transactional outbox pattern, compared the two queue backends, and drafted [A6](DECISIONS.md#a6--background-refresh-with-bullmq-and-redis-closed) and [A7](DECISIONS.md#a7--transactional-job_outbox-for-reliable-dispatch-closed). Alayala corrected the earlier extraction-focused proposal to cover the full pipeline and chose Redis over AI's PostgreSQL-backed queue recommendation. AI updated the earlier open execution references and kept implementation status explicit.

Verification covered the document diff, unique decision IDs, local links and anchors, and preservation of prior content. No application implementation, dependency installation, database migration, EIA request, queue test, or performance measurement was performed. See the [worker and outbox session](ai/sessions/2026-10-02-redis-bullmq-outbox-data-contract.md) for the supporting record and next action.

## Clerk and application model draft — October 2, 2026

[ME] Alayala selected Clerk and requested continued work on application data models. [YOU] AI recorded A8, checked Clerk's official metadata-based role guide, and drafted application models tied to setup, refresh progress, validation, approval, and publication. The schema remains proposed. AI distinguished outbox delivery from stage execution and corrected the earlier assumption that three logical datasets require exactly three files.

Document verification covered a unified diff, A1–A8 index/heading agreement, local links and anchors, and preservation of existing content. No application code, migration, provider configuration, queue execution, or authentication test ran. See the [model draft and session](ai/sessions/2026-10-02-clerk-and-application-models.md).

## Session evidence

- [A4: application state and outage queries](ai/sessions/2026-10-02-a4-state-and-outage-queries.md)
- [Creation of the document baseline](ai/sessions/2026-10-02-document-baseline.md)
- [Data findings and session handoff](ai/sessions/2026-10-02-data-findings-and-handoff.md)

Source: the current conversation and `Software Engineer - Technical Challenge.pdf`, page 3.

## Repository import — October 2, 2026

[ME] Alayala selected the private repository name `trinity`, approved the document inventory and delivery structure, excluded three personal files, and explicitly authorized AI to create the repository and make the commits.

[YOU] AI prepared the selected documents in a separate local repository folder and executes the authorized Git operations. The Obsidian originals and data workspace remain unchanged. AGENTS and CLAUDE are regular files. Four focused import commits separate repository boundaries, decisions/product, data findings, and the final handoff. Their timestamps reflect the actual commits; October 1–2 work dates remain in the original records. This is an import of existing work, not a reconstructed development history or evidence of new application implementation.

Validation and evidence limits are recorded in the [import session](ai/sessions/2026-10-02-trinity-repository-import.md). Historical data checks remain attributed to their original sessions. No new EIA request or application test is part of this documentation import.

## Data contract v1 — October 2, 2026

[ME] Alayala requested: “finalize the data contract.” [YOU] AI specified the analytical schema, validation rules, application-state model, and ER diagrams in [docs/schema.md](docs/schema.md), with the choice and alternatives recorded as A9. New defaults are attributed to AI's delegated specification work; no independent author verification is claimed.

The review corrected two concrete draft errors: freezing the data end date at request creation would require EIA work before the background worker; ordering publication by run sequence alone could still shrink the active date window. The final contract freezes the end once in the worker and rechecks coverage during the publication transaction. Publication approval also uses a durable outbox handoff to a worker, preserving A6.

Verification is limited to document consistency, links/anchors, decision references, preserved historical records, and whitespace. No application tests, database migrations, live EIA extraction, or replay of the historical exports ran. See the [contract session](ai/sessions/2026-10-02-data-contract-v1.md) for scope and remaining work.

## Vault reconciliation and session close — October 3, 2026

[ME] Alayala reaffirmed Clerk after comparing local login, corrected the AI's claim that the Parquet contract still needed definition, reported PR #1 merged, and requested a separate PR for relevant Obsidian material. He did not select Python or another runtime stack. [YOU] AI verified the merge, compared the selected vault documents with the merged repository, and adapted the field explanations into the [application model guide](docs/application-model-guide.md).

Concrete correction: AI had assessed the older vault draft without consulting PR #1, reported missing schema/behavior work already covered by that PR, and assigned a conflicting vault A9 to the active pointer. The repository's A9 and `docs/schema.md` remain authoritative. The pointer is already part of that contract; this follow-up adds no new decision ID or schema rule. The guide consolidates the duplicate validation explanation and includes the existing approvals model. The vault originals remain unchanged.

Verification covers the diff, relative links/anchors, guide fields against the canonical schema, unchanged historical sessions and contract, source-file hashes, and a bounded secret-pattern scan. No runtime tests, migrations, extraction, provider configuration, or historical-data replay ran. AI performs the requested commits and PR operations under the user's explicit authorization; these must not be attributed as manual Git work by alayala. See the [session handoff](ai/sessions/2026-10-03-vault-reconciliation-and-handoff.md).

## Python backend selection — October 3, 2026

[ME] Alayala accepted Python for the backend API and workers. [YOU] AI recorded A10 and aligned the current README and agent guidance. FastAPI remains a recommendation; package/version choices and the API/security contract remain open. This is a language decision, not application implementation.

[YOU] AI checked official library documentation and the BullMQ Python development source during the discussion. An exposed concurrency method does not prove compatibility of a released package or correct worker recovery. Document checks and remaining validation are recorded in the [Python decision session](ai/sessions/2026-10-03-python-backend-selection.md). No dependencies, runtime tests, commits, or remote changes are part of this task.

[ME] Alayala subsequently accepted FastAPI for the backend HTTP API. [YOU] AI recorded A11, aligned current guidance, and preserved the earlier decision history. Driver/migration choices and the API/security contract remain open. See the [FastAPI follow-up](ai/sessions/2026-10-03-python-backend-selection.md#fastapi-follow-up) for checks and the next decision.

[ME] Alayala then requested a continuing backend decisions/architecture branch and two commits for the existing changes. [YOU] AI created `docs/backend-decisions-architecture` from the current handoff branch and split the documentation into Python (A10), then FastAPI (A11). This authorizes these local Git operations; it does not accept the proposed database tools or request a push/PR. Later backend decisions will continue on this branch.

[ME] During that work, alayala also accepted Psycopg 3 and Alembic. [YOU] AI recorded A12 and included it with FastAPI in the second slice, preserving the requested two-commit split. Dependency versions, migrations, and runtime verification remain pending. The [database tools follow-up](ai/sessions/2026-10-03-python-backend-selection.md#database-tools-follow-up) records this updated scope.

## Proposed stack review — October 3, 2026

[ME] Alayala supplied his Obsidian `Backend Stack.md` for review before settling the stack and folder architecture. [YOU] AI compared it with the current decisions, data contract, challenge PDF, and official library documentation. AI initially treated “locally” as a same-machine storage constraint and recommended disk storage with S3 deferred. Alayala corrected that interpretation; the recommendation is withdrawn as described below.

[YOU] AI drafted a bounded folder layout and SQL rejection examples in the [stack review session](ai/sessions/2026-10-03-backend-stack-review-and-layout.md). The source note, earlier decisions, and schema are unchanged. Library documentation and document checks do not prove parser compatibility, authorization, or runtime behavior. No implementation, dependency installation, commit, or push is part of this review.

### AI interpretation error — application-owned storage

[YOU] AI over-interpreted the brief's word “locally” as requiring machine-local disk and presented the proposed S3 architecture as leaving a requirement unmet. [ME] Alayala identified the error: the intended boundary is application-owned persisted data, so exploration does not need to fetch observations from the external EIA source. S3 can be the application's internal storage provider.

[YOU] AI withdrew R1 and the disk-only recommendation, recorded the clarified storage decision as A14, and aligned the current README. This is an engineering interpretation correction, not an EIA anomaly; `FINDINGS.md` is unchanged. The correction was established through alayala's explanation and the existing separation of refresh from published-data reads, not a runtime test.

[ME] Alayala explicitly accepted PyArrow, DataFusion's Python binding, and SQLGlot. [YOU] AI recorded A13. Versions, SQL policy details, and runtime verification remain open. The next discussion is folder structure; the layout in the supporting session remains proposed, with no implementation folders created.

[ME] Alayala then proposed the feature-based folder tree, including separate query execution, publication, settings, adapters, workers, connector, and shared contracts. [YOU] AI reviewed its ownership against A9 and recommends the author's layout with explicit query authorization/isolation, shared transaction ownership, final-manifest validation, and durable recovery responsibilities. The [folder review](ai/sessions/2026-10-03-backend-stack-review-and-layout.md#author-folder-proposal-review) distinguishes conditional implementation failures from demonstrated defects. Folder selection remains pending; no application files were created.

## Backend structure accepted — October 3, 2026

[ME] Alayala accepted his proposed file structure with the five reviewed refinements and requested backend documentation under `docs/`. [YOU] AI recorded A15 and created [docs/backend.md](docs/backend.md), preserving the author's feature/file names and adding `workers/recovery.py`. AI mapped all ten application models to persistence owners and documented the query handoff, process supervision, shared transaction scope, final-manifest validation, and durable recovery boundaries.

[YOU] AI aligned README and agent guidance and recorded the [acceptance session](ai/sessions/2026-10-03-backend-structure-accepted.md). This is documentation of the accepted architecture, not generated application code or proof of runtime correctness. No dependencies, implementation folders, migrations, commits, or remote changes were produced by this task. Earlier pending-selection statements remain historical.

## API security and dependency proposal — October 3, 2026

[ME] Alayala asked to define API/security contracts and dependency versions using best practice. [YOU] AI traced current A9–A15 and drafted [the contract proposal](docs/api-contract.md), with A16–A17 explicitly proposed rather than accepted. It defines endpoint behavior, permissions, Clerk session/role checks, narrow SQL, error handling, durable mutations, starting limits, and exact candidate releases. The single-table SQL restriction and uncached Clerk lookups are AI recommendations requiring author review.

[YOU] AI read official documentation and public PyPI release metadata. The network sandbox blocked the initial registry request; the approved read-only retry succeeded and installed nothing. Metadata comparisons do not prove dependency resolution, security, or runtime compatibility. The [proposal session](ai/sessions/2026-10-03-api-security-dependency-proposal.md) records document checks and pending work. No EIA key, runtime build/test, database/cloud change, commit, or push was used.

## Dependency versions accepted — October 3, 2026

[ME] Alayala approved the dependency versions and requested the decision update, commit, and push. He keeps the API and security contracts under review. [YOU] AI recorded A17 as accepted with the unchanged exact version table in DECISIONS.md and the lockfile/update policy. Pool execution choices and numeric limits remain proposals; version acceptance does not prove compatibility.

[YOU] AI prepared a dependency-only commit from the mixed documentation work. API/security proposal text and the human overview stay local for review. No packages were installed and no runtime checks ran. The [acceptance session](ai/sessions/2026-10-03-dependency-versions-accepted.md) records scope, document verification, and publication boundaries.

## SQL scope accepted — October 3, 2026

[ME] Alayala supplied and accepted the two-stage SQL scope. [YOU] AI recorded [A18](DECISIONS.md#a18--sql-scope-by-stage-closed) and aligned current references while preserving the rest of A16 as proposed. Exact function approval and implementation remain pending. See the [SQL scope session](ai/sessions/2026-10-03-sql-scope-by-stage.md) for document checks and the remaining boundary. No commit, push, or runtime test was performed.

## Approved API contract expanded — October 3, 2026

[ME] Alayala supplied his approved high-level API design and asked for missing requests, responses and fields. [YOU] AI expanded docs/api-contract.md, added docs/openapi.json for all 20 operations, recorded A16 as accepted for the author's flow, and aligned current product/application-state documentation. The source download is preserved. Exact schema fields, bounded defaults, diagnostic severity mapping and recovery persistence details are AI-authored completion work, not independently observed user verification.

[YOU] AI preserves A17 dependency versions and the separately added A18 staged SQL decision. API approval does not select the detailed authentication mechanism, SQL function allowlist, or runtime sandbox. The [completion session](ai/sessions/2026-10-03-approved-api-contract-expanded.md) records source provenance, changes, checks and remaining tests. No new commit/push or application implementation was requested.

## Security contract and API split — October 3, 2026

[ME] Alayala selected the security mechanisms, limits, retries, SHA-256 identity and local Docker Compose direction and requested separate API/security documents. [YOU] AI retained accepted A16, recorded A19, renamed the API document and updated references, created the security contract and aligned OpenAPI/schema/backend guidance. Older conflicting proposals are preserved as superseded history. A17 versions and existing user changes are preserved.

[YOU] AI checked the supplied challenge PDF: local execution and a repository link are required; no public application URL requirement was found. Documentation/structural checks and remaining runtime work are recorded in the [split session](ai/sessions/2026-10-03-security-contract-and-api-split.md). No code, packages, containers, commits, push or cloud changes were produced. Local isolation and capacity measurements still require implementation and execution.

## Backend contract publication — October 3, 2026

[ME] Alayala requested focused commits, push and merge to main. [YOU] AI executes those authorized Git operations in two documentation slices and preserves the existing incremental branch history. Repository inspection confirms that backend implementation and runtime tests remain pending. See the [publication session](ai/sessions/2026-10-03-backend-contracts-publication.md) for scope, validation and the distinction between the completed design and executable work.

## Local authentication design amendment — October 3, 2026

[ME] Alayala replaced Clerk with reproducible local authentication and requested a focused branch from main. [YOU] AI checked the current main baseline, amended A8/A19 and the affected setup/dependency/backend/API/security notes, and explicitly specified two auth tables and login/logout endpoints. Server-side persona permissions and unrelated data/job/publication decisions remain unchanged. Concrete defaults are attributed to AI completion work. No auth implementation or runtime security result is claimed. See the [session record](ai/sessions/2026-10-03-local-authentication-design.md) for verification and remaining implementation gates.
