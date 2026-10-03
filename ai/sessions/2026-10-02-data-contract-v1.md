# Session — Data contract v1

Date: October 2, 2026. Timezone: America/Merida. Scope: finalize the data specification for `alejandroayalad/trinity` from baseline commit `df5e5b0ab9d00297ea70389d60cf8044238301fe`.

## Objective and contributions

[ME] Alayala requested a GitHub project review, then instructed: “finalize the data contract.” [YOU] AI read the current repository documents and supporting sessions, checked EIA and Parquet documentation, and wrote the canonical specification and ER diagrams in [docs/schema.md](../../docs/schema.md). [A9](../../DECISIONS.md#a9--data-contract-v1-finalized) records the resulting rules, alternatives, and new defaults. README, PRODUCT, FINDINGS, NOTES, and AGENTS now point to the current contract. Earlier session records remain historical and unchanged.

This is delegated specification work. It does not claim that alayala selected each detailed default separately, wrote implementation code, or passed a comprehension check. Source observations and hypotheses remain distinct from the new rules.

## Decisions and scope

A1–A8 are preserved. The specification fixes daily keys, text source IDs, decimal storage, missing observations, same-day metrics, full-window refresh, required/diagnostic checks, version evidence, the ten state models, and consistent publication. Backend language, framework, SQL grammar and table detection, token verification, execution limits, and an age-based stale threshold remain separate implementation work. Source methodology and self-contained historical reproduction remain unresolved evidence tasks.

New limits are explicit: history begins at the wider inspected export's 2024-10-02 start; exact MW reconciliation uses zero tolerance; source numbers must fit DECIMAL(24,6) exactly; published files are retained for v1. These are Trinity defaults, not general EIA guarantees or measured performance conclusions.

## Draft corrections

1. The initial draft both discovered the end in a worker and required it at request creation. The final rule freezes the requested start and end strategy with the request, then resolves/freezes the end once in the worker before extraction. Retries retain that end.
2. A monotonic run sequence alone did not prevent a newer request with older source coverage from shortening the active history. Publication now rechecks coverage containment under the active-pointer lock.
3. Approval must not execute a pipeline in an HTTP request. It commits approval, publishing state, and a publication outbox request together. A worker performs publication with a fresh execution fence. Redelivery cannot restart extraction for a publishing run.

Independent read-only reviews examined analytical policy and application-state rules. No extra agents, roles, or tools were added to the project itself.

## Checks and evidence limits

Document verification checks relative links and anchors, balanced code fences, unique decision headings, the required validation-check inventory, preserved earlier session files, and whitespace in the diff. The compact Mermaid diagrams were reviewed as source; no diagram-rendering package was available in this environment. These checks do not validate Parquet IO, migrations, queue behavior, SQL authorization, or authentication.

Result: 92 relative links/anchors resolved; seven code-fence pairs were balanced; A1–A9 headings were unique and ordered; V01–V08 define 16 required result rows; all ten prior session files were unchanged; the diff had no whitespace errors. A bounded token-pattern scan found no matching GitHub tokens or private-key headers. This scan is not proof against every secret format.

No EIA key was used, no data API extraction was performed, and historical CSV checks were not rerun. Public EIA documentation confirms string values, sorting, pagination, and request echoes that require credential removal. Parquet/Arrow documentation supports the chosen logical representations; the selected precision remains a project boundary.

The change is documentation only. Preserve the original four import commits. The GitHub review branch contains a new focused commit; no squash, history rewrite, deployment, or main-branch merge is part of this task.

## Next action

Choose the runtime stack and implement one verified extraction → validation → Parquet → DataFusion query slice using this contract. Maintain data evidence — ongoing. Complete SQL/authentication contracts before implementing those access paths.
