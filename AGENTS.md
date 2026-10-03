# Shared agent instructions — Trinity

These rules apply to work in this documentation folder and to their later use in the project repository. Follow the user's current request. Accepted decisions do not by themselves authorize implementation.

## Read the relevant context

1. Read `README.md` for current project scope and document roles.
2. Read the applicable entries in `DECISIONS.md`. Do not treat an open question as an accepted choice.
3. For data work, read `FINDINGS.md`. For product behavior, read `PRODUCT.md`.
4. Read the relevant latest record in `ai/sessions/` when continuing prior work. Historical logs do not override newer decisions or user instructions.
5. Inspect the actual files and repository status before edits. Preserve existing user work.

## Work with alayala

Use common words, short sentences, and active voice. Use ASD-STE100 as a guide; do not claim formal compliance. Preserve exact code identifiers. Explain necessary technical terms.

Before a code change, explain the input, data flow, expected output, and one failure case. Keep the explanation tied to the requested task. After a meaningful change, support a short check of alayala's understanding. Do not claim that he understands code without an observed explanation.

Distinguish analysis, implementation, review, and debugging. Stay in the requested mode. Use bounded tasks and state assumptions that affect the result. Do not create extra plans, abstractions, support documents, subagent roles, or skills without a concrete need. Delegate only when the user or applicable instructions explicitly request it.

## Keep alayala in the loop

This is required, not optional.

- Start every reply with: `📍 <Phase> · <Title> · Next: [ME|YOU] <one action>`. Phases: Data, Decisions, Build, Review, Live prep.
- [ME] is alayala: decisions, commands that use the EIA key, builds and clicks, commits, and work the evaluator must see as his. [YOU] is the agent: code tracing, drafts, read-only checks, diff review, evidence notes. Use these tags in `NOTES.md` contributions.
- Keep replies to about 15 lines unless he asks for detail. Lead with the answer.
- For a decision, trace the code or data first. Give one recommendation with evidence and one yes/no question. If new evidence changes it, say "my recommendation changes" and why.
- Ask one question at a time. When he needs to act, give one small action (exact command or click path), then stop and wait.
- If he drifts to another topic, answer briefly, then name the current task.
- At each gate, show a 3-line checkpoint: done / pending / blocker.

## Selected boundaries

PostgreSQL stores application state. Apache DataFusion executes outage queries over published Parquet datasets. User SQL must not expose application-state tables or unpublished files. See A4 for the rationale and open technical details.

A2 requires scheduled and manual Admin refreshes. A3 requires initial shared-account setup and editable schedule. A16 supersedes selectable publication modes: required checks plus no review warnings publish automatically; warnings require Admin approval; required failures/incompletion block publication. Setup is not repeated per Admin. A16 serializes the full refresh lifecycle and defines warning recovery, same-candidate publication retry and permanent discard. Read docs/api-contract.md and docs/openapi.json for the approved flow and detailed API schemas; read docs/security-contract.md for accepted A19 security rules and remaining implementation details.

Read A9 and `docs/schema.md` for the finalized data contract, keys, metric fields, validation, and publication invariants. A10 selects Python for the backend API and workers; A11 selects FastAPI for the HTTP API; A12 selects Psycopg 3 and Alembic for PostgreSQL access and migrations. A17 selects exact dependency versions and the lockfile/update policy; compatibility checks remain pending. A18 selects staged SQL scope; A19 selects roles, SQL function names, per-query network-disabled containers with authorized read-only Parquet mounts, PostgreSQL query admission, limits, retries and Docker Compose locally. Frontend, exact token/parser/container configuration, rate accounting, refresh-stage deadlines and public hosting remain unresolved. Runtime verification is pending. Do not silently choose them because a library example uses a particular language or schema. A9 is an AI-authored specification under delegated work, not proof of user verification or runtime correctness.

A13 selects PyArrow, datafusion-python, and SQLGlot. A14 retains application-owned S3 storage: “locally” means persisted data under application control, independent of live EIA requests during exploration. Do not reintroduce the withdrawn disk-only interpretation. A15 accepts the feature-based backend structure and five responsibility refinements in `docs/backend.md`; read it before backend implementation or architecture changes. The file tree is selected but not implemented.

## Evidence and data

Separate requirements, accepted choices, observations, hypotheses, and unverified claims. Do not turn an example into a finding.

Before describing a dataset as complete, verify pagination and coverage. Preserve source values when investigating anomalies. Record periods, entities, units, values, gap sizes, retrieval details, and reproducible queries or code. A missing value does not establish zero outage.

Keep credentials out of documents, logs, examples, command output, and version control. Do not copy private credential notes into project artifacts. Use configured environment variables for secrets. Redact secret-bearing URLs and error output.

## Ongoing anomaly workflow

Treat data evidence as ongoing work, not a phase that ends after three anomalies. Three is the submission minimum, not a limit. Keep [FINDINGS.md](FINDINGS.md) current as data is fetched, reviewed, or used during implementation. Report completed checks as completed; track remaining baseline requirements separately from future discoveries.

When a potential anomaly appears:

1. **Check whether it is already recorded.** Read the existing anomalies and supporting history. Extend an existing entry when it is the same issue. Do not reopen a rejected candidate without new evidence.
2. **Record the candidate.** Add a short entry under “Potential anomalies” in FINDINGS.md; create that section only when needed. Use a unique `CAND-01` style ID and status `unverified`. Include the date, route, plant/unit if applicable, expected behavior, observed values, source file or response, and why it matters. Record missing evidence explicitly. Recording a candidate does not require a separate approval.
3. **Verify it.** Run a small reproducible check. Preserve the original values and command or query. Check coverage and duplicates where relevant. Separate a confirmed observation from its possible cause; use an official source for explanations when available. Mark the candidate `verified`, `not an anomaly`, or `unresolved`, with the reason.
4. **Review the result with alayala.** Explain it in plain language and propose product handling. When he selects it, move it into the numbered AN section with the next unused ID and link its evidence. If he has already selected it, proceed without asking again. Keep rejected or unresolved evidence in the supporting session rather than silently presenting it as confirmed.
5. **Keep the record consistent.** Update counts and current status. Link any proposed change in product behavior to DECISIONS.md; only an accepted choice becomes a decision. Record human/AI contributions in NOTES.md and the session. Do not implement a fix or change publication rules merely because an anomaly was found.

Use the short anomaly format already in FINDINGS.md: what happened, what we checked, why it matters, what explains it or remains unknown, proposed/accepted product handling, and how to repeat the check. Put long commands and tables in the linked evidence note. Keep unknown causes visible without discarding verified observations.

In plans, call step 1 **“Maintain data evidence — ongoing.”** Do not mark this ongoing process closed just because the current anomaly list is sufficient. This does not waive submission requirements or make every new candidate a blocker; state which concrete decision or validation requirement a candidate affects.

## Verification and changes

Review the diff. Run the smallest relevant checks supported by the repository. For code defects, add a regression test when practical. For document changes, check consistency, links, and preserved user content. Do not claim a check passed unless it ran.

For a code-review finding, state severity and scope, expected behavior, observed behavior, execution or data flow, a concrete failure case, recommended correction, and validation still needed. Use relative paths with named methods or data objects. A path alone is not evidence.

Do not commit, push, open a pull request, or change remote state unless requested. When commits are authorized, use incremental commits and explain why. Arkham requires history without squashing or rewriting it. Ask before destructive or irreversible actions. Respect sandbox approval requirements for external writes.

## Documentation and handoff

`DECISIONS.md` is the single decision record. Keep unique IDs and the two agreed categories. Record changed decisions with their history. Link evidence instead of duplicating decision text across files.

`FINDINGS.md` holds data evidence. `NOTES.md` summarizes AI use and verification for the evaluator. Session records hold dated supporting history. `CLAUDE.md` points here and must not duplicate these rules.

Use a unique descriptive filename for each session. Record objective, human and AI contributions, decision references, corrections, checks and results, open questions, and one next action. Never overwrite another session merely because the date matches.

Do not treat project-specific access tokens or unrelated personal material as task context. A session summary is not a verbatim transcript or proof of runtime behavior.
