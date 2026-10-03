# Session log — Validation controls publication

Date: October 2, 2026. Scope: product decision and documentation.

## Objective and contributions

[ME] Alayala challenged the proposed warning for AN-03: if counts and required checks pass, validation should accept the data; otherwise it stays unpublished. [YOU] AI recorded this as A5 and updated the two current handling paragraphs in FINDINGS.md. Earlier investigation records remain historical evidence.

## Decision and correction

[A5 in DECISIONS.md](../../DECISIONS.md#a5--validation-decides-whether-data-is-ready-closed) is the single accepted rule. The previous AI proposal to keep a user-facing warning after successful validation was rejected. The observed API total mismatch remains factual evidence; A5 changes the product response to it.

A2 preserves the previous valid version while a replacement is unready. A3 still controls automatic publication versus Admin approval after validation. A4's storage responsibilities remain unchanged. No separate service deployment, validation tolerance, or backend technology was selected.

## Verification

The change is documentation only. Checks cover unique A5 identity, preserved A1–A4 text except the A2 cross-reference, links, Markdown code fences, and removal of the obsolete warning instructions from current AN-03 handling. Diffs are reviewed before writing; saved files are compared with the reviewed drafts. No API requests, application changes, runtime tests, commits, or pushes occurred.

## Remaining work

Define the exact required data checks and tolerances, implement validation, and verify success, failure, first-load, and approval behavior. This decision does not claim that the data phase or application is complete.

Next: define the required validation checks.
