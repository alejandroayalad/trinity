# Dataset preview Step 5 — operator tooling and delivery handoff

## Authority and outcome

[ME] Alayala authorized Step 5, closure, commits and push to the current `feat/catalog-permissions` branch after reviewing Step 4. [YOU] Implemented the optional operator checker and preserved the existing default/auth/catalog checks. Closure means delivery of the implemented work with an explicit incomplete operator gate; it does not certify a retained publication or authorize inventing one. No conceptual explanation by alayala is inferred.

The [Step 4 result](2026-10-04-dataset-preview-step-4-acceptance.md#final-checkpoint) remains historical evidence for its exact code/test scope. Current Step 5 results appear below. No production dependency was added. Comments describe behavior and specific conditions.

## Input, processing, output and failure

`trinity.auth.check --preview-fixture PATH` reads a private, bounded JSON fixture before prompting for passwords. `PreviewFixture` requires one publication identity, date range, exact facility/generator IDs, two ordered expected rows per dataset and exact scoped diagnostic summaries. It reuses canonical preview schemas. The fixture's size is bounded to 128 KiB.

For each retained persona, login obtains an in-memory token. Viewer must read two national pages and receive 404 `dataset_not_found` for both detail datasets. Analyst and Admin must read two exact pages of every dataset, applying facility and generator filters. Each successful preview response must match the known publication, range, values and frozen summaries and carry the required headers. The first page must have a real continuation cursor; the second must match the next expected row. The token and cursor are never printed. The `finally` path attempts logout even after a failed preview; successful flows verify post-logout denial.

Missing/invalid fixture, unavailable published preview, empty results or missing continuation produce `not ready/incomplete` and exit 2. Other check failures exit 1; cancellation exits 130. No response body, exception text, secret, cursor or fixture path is printed on failure. Default and `--catalog` modes retain their prior behavior. A synthetic fixture can test tooling but cannot establish retained-account evidence.

## Confirmed retained-environment boundary

- **Severity and scope:** delivery blocker; retained local deployment, not a failing disposable acceptance test.
- **Expected:** a known active publication, migrations through 0004, frozen provenance linkage and configured matching preview runtime before the retained operator pass.
- **Observed:** the running `trinity-postgres-1` database reports migration `0002_app_entry`, zero rows in `publication_events`, and zero non-null pointers in `active_publication`. `create_app` in `backend/src/trinity/main.py` still defaults `enable_preview=False`.
- **Evidence:** a `BEGIN READ ONLY` transaction queried only `alembic_version`, the publication event count and the active-pointer count, then committed. No password/secret file was read or printed. Inspection of `backend/src/trinity/publication/` found read methods in `repository.py` and `read_preview_diagnostics` in `diagnostics.py`; searching function declarations found no publication writer. `compose.yaml` supplies the auth/API deployment, not the preview runtime configuration.
- **Failure scenario:** a persona targets the retained API with the fixture below. There is no active publication to bind its cursor or evidence; successful published preview cannot be established. Copying the test seed into this database would fabricate the missing prerequisite.
- **Required correction:** implement/verify the approved refresh/publication lifecycle and trusted frozen references; separately migrate/configure the retained deployment and activate only an authorized validated version. This is not part of the preview checker.
- **Validation still required:** the retained Viewer/Analyst/Admin run against that publication. No retained migration, key setup, image rebuild, publication or live EIA/S3 operation occurred here.

## Concrete candidate for a future operator fixture

[YOU] Read the existing local candidate `9dcc2cc8-7b5f-4b7d-8bd8-5a94f211a0ae`. The local manifest matched the committed [manifest](../../evidence/live-preparation/2026-10-04-october-1-2/manifest.json) byte-for-byte. Every listed Parquet file matched its manifest size and SHA-256 before rows were read. This reuses retained evidence; it does not create a publication. No new anomaly or completeness claim was introduced; maintain data evidence — ongoing.

The proposed fixture uses October 1–2, 2026, `facility="1715"` (Palisades), `generator="1"`, and page size 1. The two daily keys per dataset ensure a second page. These are verified candidate values, **not an authorized active-publication selection**:

| Dataset | First expected row | Second expected row |
|---|---|---|
| national_outages | `["2026-10-01","100056.700000","11988.606000","11.980000"]` | `["2026-10-02","100056.700000","12295.214000","12.290000"]` |
| facility_outages | `["2026-10-01","1715","Palisades","815.600000","815.600000","100.000000"]` | `["2026-10-02","1715","Palisades","815.600000","815.600000","100.000000"]` |
| generator_outages | `["2026-10-01","1715","1","Palisades","815.600000","815.600000","100.000000"]` | `["2026-10-02","1715","1","Palisades","815.600000","815.600000","100.000000"]` |

After this exact candidate is legitimately published, create a private JSON file outside Git with these fields:

- `publication`: the complete authoritative `Publication` object (`publication_event_id`, `version_id`, `published_at`, `coverage_start`, `coverage_end`, `latest_observation_date`). Its version must match the selected candidate. No event ID or publication time exists to fill in now.
- `range`: `{"start":"2026-10-01","end":"2026-10-02"}`; `facility`: `"1715"`; `generator`: `"1"`.
- `rows`: object keyed by all three public dataset names; each value is the two-row array above in order.
- `diagnostics`: object keyed by all three public dataset names; each value is the independently verified frozen dataset summary projection (`code`, `severity`, `scope`, `message`, `affected_count`). Include affected public summaries only, never D09 or raw details. An empty list is valid only if verified for that dataset; do not replace missing evidence with empty lists.

If a different version is published, obtain its independently verified rows and frozen summaries instead. Do not copy expectations from the endpoint being tested. The checker never seeds, publishes or enables preview.

Once those prerequisites exist, the operator runs from the repository root:

```sh
backend/.venv/bin/python -m trinity.auth.check --catalog --preview-fixture /absolute/private/preview-fixture.json
```

Passwords are prompted privately. Exit 0 establishes only the observed configured run. At present this command is not a ready-to-run retained acceptance step because there is no publication fixture.

## Verification and delivery

The initial seven focused checker tests passed in 0.110 seconds. They cover all roles, exact pages/filters, default-mode preservation, logout on failure, incomplete prerequisites, corrupted/mismatched evidence, repeated pages, bounded fixtures and safe CLI failures. Full regression and real loopback/Docker results are recorded after completion below.

[YOU] Prepared three incremental commits: typed integration/evidence reader, database/container acceptance, then operator checker/documentation handoff. This preserves the branch's existing seven commits ahead of its fetched remote without squashing or rewriting history. Push is explicitly authorized by alayala; no PR or merge was requested.


## Closure checkpoint

- Focused checker tests: **7 passed**, 0.110 seconds.
- Full offline regression: **440 discovered, 363 passed, 77 opt-in skips**, 49.499 seconds.
- Explicit combined SQL/preview/auth/catalog PostgreSQL/HTTP/Docker regression: **72 passed, zero skips**, 274.034 seconds. All 15 preview runtime cases passed, including the new operator checker with independent producer-row and diagnostic expectations for all personas.
- The unchanged standalone SQL container/frame suite passed 7/7 in Step 4. Together, the recorded suites cover **440 distinct passing tests**; two frame cases overlap. The 77 offline skips are covered by 72 combined cases plus five standalone container cases. This is coverage across separate runs, not a single all-runtime command.
- Scoped diff review, 32 changed/new Python syntax checks, whitespace checks and local Markdown link/anchor/fence checks passed. No formatter/linter/type-check command is configured. The existing Starlette/httpx warning remains without a dependency change.

Done: implementation and operator tooling delivered for commit/push on the existing branch; automated evidence passed.
Pending: the retained-account operator run and human explanation of cursor/permission/publication identity.
Blocker: retained publication workflow/linkage and deployment prerequisites. Migrations alone do not create a publication. Preview remains disabled; the candidate stays unpublished.
Next: implement the approved refresh/publication slice, then revisit retained preview acceptance. The current implementation handoff is closed with this gate explicitly incomplete.
