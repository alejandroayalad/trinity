# Phase 3 — Findings scripts and preserved inputs

Date: October 4, 2026. Branch: `main`. Mode: implementation and review.
Status: local reproduction verified; Git delivery authorized; maintain data evidence — ongoing.

## Objective and contributions

[ME] Alayala requested reuse of the existing report and recorded checks, explicit
inputs/checksums, reconciliation over at least 30 days, AN-01–AN-03, weighted
percentages and daily keys, synthetic logic tests, and measured results from saved
real EIA data. The Phase 2 live gate remains separate. He clarified that the existing
AWS setup needs proof from a real run, not replacement resources. Authentication
and protected routes are the next implementation slice, outside this change.

[YOU] AI inspected repository instructions, contribution rules, the current
decisions/contracts, findings, historical checks, and the original report script.
The working tree was clean before the slice. AI adapted the useful methods, copied
only reviewed public-data exports and previously sanitized responses, wrote tests,
ran the checks, and updated documentation. No subagents were used. Original data
fetching and initial findings remain Alayala's contributions; AI's implementation
and reruns do not establish his independent code walkthrough or understanding.

Decision references: A5, A9, A14, A15, A17. No decision changed. The offline analysis
command does not become a second connector or change application publication rules.

## Inputs, flow, and output

The [input manifest](../../evidence/findings/inputs/manifest.json) identifies three
CSV exports covering 2024-10-02–2026-10-02 and nine API responses captured on
October 2. Files were copied without altering bytes. A targeted credential-pattern
scan reported no matches, and the reviewed CSV columns and JSON structures contain
the public analytical fields and key-free request evidence. No downloader, private
configuration, source credential note, or historical manifest was copied.

The January 1, 2025–October 2, 2026 original exports were compared row-for-row with
the corresponding bundled subwindow: 640 national, 34,949 facility, and 60,549
generator rows matched, including source text. Those shorter exports are not
duplicated. The reproduction command does not depend on their external location.

`scripts/generate_report.py`: verify all input hashes → parse unique daily rows and
exact decimal values → report coverage → reconcile units with facilities and each
grain with national totals → calculate selected anomalies/supporting examples →
write `REPORT.md`, `report.json`, and every comparison in `reconciliation.csv`.
Each analysis has its own function. No third-party dependency is needed.

A missing group stays missing, even when its peer reports zero. A missing date or
99.9% observation breaks a confirmed full-outage run. A changed input fails before
output creation. Empty API probes must use the matching dates, filters, sorting,
and actual CSV end offset; one-day totals must agree across the paired probes.
An existing output directory is preserved. A write failure returns nonzero; a
partially written new output directory is not successful evidence.

The old script's fixed causal explanations, 0.0005 MW outage tolerance, and 99.9%
full-outage threshold were not carried forward. Its useful Decimal aggregation,
calendar continuity, facility membership, identity, and percentage methods were
adapted along with the already executed session checks. This is a reviewed reuse,
not a fresh source investigation or proof of EIA's internal calculations.

## Checks and results

| Check actually run | Result |
|---|---|
| `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_findings_report.py -v` | 17 synthetic tests passed |
| `backend/.venv/bin/python -m unittest discover -s backend/tests -q` | 202 tests passed in 27.079 seconds; existing Starlette/HTTPX deprecation warning |
| `backend/.venv/bin/python scripts/generate_report.py --out backend/artifacts/findings-phase3-verified` | Exit 0; all 16 historical claim checks true |
| Exact real-data reconciliation | 79,726 unit-to-facility + 2,924 lower-grain-to-national comparisons; 82,650 differences equal 0 MW |
| AN-01 | +2,436.2 MW; same 55 facilities; 47 increased, 8 unchanged |
| AN-02 | First observed 2025-09-09; 389 consecutive fully offline records through 2026-10-02; generator 1 agrees; 54 other facilities present every day |
| AN-03 | Facility one-day 95 advertised / 55 returned; Browns Ferry 3 / 1; empty probes at offsets 55 and 39,863; two-year total 69,103 |
| F1 / F2 | Millstone weighted 40.95%, simple mean 50%; generator 1 at 47 facilities on 2026-09-15 |
| Original shorter CSVs versus bundled subwindow | Every parsed row and field matched |

The complete measured output is retained in
[REPORT.md](../../evidence/findings/REPORT.md) and
[expected-report.json](../../evidence/findings/expected-report.json), including
the comparison CSV hash and all input hashes. These values came from the real
saved inputs; synthetic tests do not supply the findings.

For isolation, AI copied the current tracked files and the explicit new script,
test, and evidence files to a temporary directory. No `.git`, `.venv`, ignored
artifacts, outside research files, or credentials were required. With an environment
containing only the system PATH, system Python 3.9.6 ran the documented command
with exit 0. Both reports matched the retained bytes exactly. The 17 focused tests
also passed there. This tests the proposed file set without changing A17 or
claiming that an unmodified clone of the current remote already contains the slice.

After the full suite, a small report robustness change made empty-window coverage
explicit and tied the two-year advertised total to the actual generator count.
The saved-data command and isolated focused tests above ran on that final code.
The backend application code did not change. No formatter, linter, or type checker
is configured for this script; no package build or dependency installation was
needed. Diff, local Markdown links/anchors, and input/report identities were checked
before handoff.

## Remaining boundaries and next action

The preserved API probes are selected responses, not all original paginated
download pages. Agreement across grains does not prove that the source has no
shared omissions. Seasonal capacity definitions, EIA revision methods, and the
internal cause of its total mismatch remain separate source questions. The
Palisades source explanation remains in FINDINGS.md; its 389-day duration is
measured from saved rows. No new candidate or product policy was invented.

The earlier Python STS attempt stopped at missing CRT support before returning an
ARN. The subsequent user command could not find `uv`. This slice neither repaired
that tooling nor changed IAM. There is still no live preparation receipt or S3
protection evidence from this work. Keep the existing profile, role, and bucket.
Phase 2 requires real EIA retrieval and S3 protection/storage/readback checks,
exit 0, and verified `evidence/preparation/result.json` with `published=false`.

Done: local Phase 3 implementation, saved-data reproduction, and isolated-tree checks.
Pending: human review of the analysis; separate Phase 2 live proof.
Blocker: none for local findings reproduction; live verification remains open.

Next: [ME] run the command in the [reproduction guide](../../evidence/findings/README.md)
and inspect AN-01–AN-03 in its output before proceeding to the next slice.

## Authorized Git delivery

Alayala subsequently requested committing and pushing the remaining work and
merging it to `main`. The checkout was already on `main` at `17864ee`, matching
`origin/main` after fetch. Only this Phase 3 slice was pending. No separate merge
is needed when these commits are created directly on `main`.

Delivery keeps two incremental commits: first the command, synthetic tests,
reviewed inputs, and retained reports; then the findings, README, schema
reproduction pointer, contribution notes, and this session. Other worktrees and
their branches remain outside the requested change. The delivery response records
the resulting commit IDs and the final local/remote verification. This Git
authorization does not mark the separate live EIA/S3 gate as passed.

The first staged whitespace check flagged the original CSV CRLF endings. The
source bytes were preserved. File-specific Git attributes disable text conversion
for checksum-pinned inputs and retained outputs and recognize CRLF endings in
those CSVs during whitespace checks. This keeps checksum identity portable to
clones configured with automatic line-ending conversion.

The implementation/evidence commit is `dcc13e3`. AI cloned that committed tree
into a temporary directory with `core.autocrlf=true`, ran the report using system
Python with only PATH in its environment, and obtained exit 0 with all 16 claims
and 82,650 comparisons reproduced. Both retained output files matched byte-for-byte.
The clone remained clean after generation. This is an actual committed-tree clone
check, in addition to the earlier pre-commit isolated-copy check.
