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
