# Session log — A4: application state and outage queries

Recorded: October 2, 2026. Timezone: America/Merida.
Scope: the architecture discussion leading to A4, across October 1–2. This is an AI-written summary of the conversation, not a full transcript or a runtime validation record.

## Outcome

A4 is accepted and closed. Use PostgreSQL for application state and Apache DataFusion for outage queries over Parquet. See [DECISIONS — A4](../../DECISIONS.md) for the decision, reason, rejected alternative, and tradeoff.

| Component | Selected responsibility |
|---|---|
| PostgreSQL | Shared settings, refresh status, approval records, and the published data version. |
| Apache DataFusion | Execute permitted SQL over published outage datasets. |
| Parquet | Store outage extracts and prepared data. No second outage-data copy in PostgreSQL. |
| Backend | Enforce permissions and query rules; coordinate refresh, validation, approval, and publication. |

## Human and AI contributions

Alayala questioned the initial DuckDB recommendation and asked for other approaches. He proposed frequent collection with a PostgreSQL load on refresh. He then selected separate tools for application state and outage queries. He explicitly requested closing A4 and recording this session.

The AI explained direct Parquet queries, compared DataFusion and PostgreSQL, and identified the difference between downloaded data and data visible to users. It drafted the decision records and this log. No project code was written by either participant in this discussion.

A2 and A3 supplied the product context: scheduled and manual Admin refreshes; one initial account configuration; daily schedule by default with time and timezone; editable shared settings; automatic publication or Admin approval after validation.

## Corrections during the discussion

- The AI initially kept explaining DuckDB instead of addressing the request for alternatives. Alayala clarified that he wanted to challenge that recommendation.
- The AI initially left scheduled refreshes open after recording automatic publication. Alayala clarified that both scheduled and manual refreshes were selected. A2 was corrected.
- Alayala required A3 as a committed feature and narrowed setup to the initial shared account, not each Admin user. The record was corrected. A3 also updated A2 to allow Admin approval as a publication mode.

These are observed corrections in the conversation. They do not prove implementation quality or retained understanding of code.

## Evidence and verification

The AI read the challenge PDF and consulted official [DataFusion SQL documentation](https://datafusion.apache.org/library-user-guide/using-the-sql-api.html), [PostgreSQL permissions](https://www.postgresql.org/docs/current/ddl-priv.html), and [PostgreSQL transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html). It reviewed document diffs and verified saved note contents.

No connector, database schema, query endpoint, or frontend was implemented. No EIA data analysis, integration test, security test, or performance measurement was performed for A4. No commit or remote change was made. The selected tools have distinct roles; their integration still needs proof.

PostgreSQL transactions do not cover external Parquet file writes. Publication must still protect queries from incomplete or mixed data versions. The user SQL path must not expose application-state tables or unpublished files.

## Handoff

A1 through A4 are closed as recorded decisions. Implementation has not started. The backend language, framework, DataFusion binding, component versions, and publication mechanism remain open. DataFusion does not imply a Rust backend.

Next discussion: identify the backend language and the matching DataFusion binding. Do not start implementation without a new instruction.
