# Session — QA-03 API activation and complete dashboard timings

Date: 2026-10-06. Mode: live preparation and runtime verification.
Basis: [A19](../../DECISIONS.md#a19--security-contract-and-local-execution-closed),
[cache implementation](2026-10-06-qa-03-cache-implementation.md),
[initial component profile](2026-10-05-qa-03-evidence-read-profile.md).

## Objective and contributions

- [ME] Alayala explicitly requested the API rebuild and the full dashboard timing check.
- [YOU] OpenCode captured a pre-rebuild HTTP baseline, rebuilt only the API,
  measured cold/warm HTTP and browser-visible timings, and checked data
  identity, role isolation and cleanup.
- [YOU] Added two secret-safe measurement scripts. Credentials came from the
  configured environment; no passwords, tokens or response bodies were saved.

## Deployment and retained state

The baseline API did not have `evidence_cache` installed. `TRINITY_PREVIEW_ENABLED`
was true and Compose validation passed. No query containers were running.

```bash
docker compose -f compose.yaml -f compose.sql.yaml up -d --build --no-deps --wait --wait-timeout 120 api
```

| Item | Before | After |
|---|---|---|
| API image | `sha256:7cc897e4…` | `sha256:aa835d66…` |
| Started | 2026-10-06T02:06:08Z | 2026-10-06T06:44:15Z |
| Evidence cache | Absent | 16 entries, 60-second lifetime |
| Health / Preview | Healthy / enabled | Healthy / enabled |

The image includes committed QA-03 through `9467b12` plus existing uncommitted
local activation changes. It is a retained-stack activation, not a clean-checkout
deployment. PostgreSQL, refresh and publication containers were unchanged. All
successful reads used publication event `6c067cb4-…`, latest observation 2026-10-05.

## Complete HTTP measurements

Start before `fetch`, end after reading the full body: authentication/admission,
evidence handling, staging, container execution/cleanup and loopback transfer.

| Request | Before, no cache | After, expected warm |
|---|---|---|
| Viewer 30 days | 4.105, 9.400, 9.872 s; median **9.400 s** | 1.644, 1.664 s; median **1.654 s** |
| Analyst 30 days | 3.896 s | 1.890, 1.861 s; median **1.875 s** |
| Admin 30 days | 5.042 s | 2.051, 1.743 s; median **1.897 s** |
| Viewer 90 days | Not sampled | **1.966 s** |
| Viewer 365 days | 6.043 s | **1.880 s** |
| Analyst facility preview | 5.013 s | 2.070, 2.093 s; median **2.082 s** |

Cold/expired: first dashboard after rebuild **7.133 s**; after 65 s idle, one
Analyst dashboard and one facility preview together took **5.595 s** and **6.046 s**.
Warm-labelled samples all started within 58 s of the first cold start. The API
exposes no cache-hit counter, so cold/warm labels follow the controlled sequence
and TTL, not an observed internal event. Samples are small: no percentile claim.

## Correctness and cleanup

- Before/after publication metadata and per-endpoint data fingerprints matched.
- Day counts (30/90/365), range end and summary matched; repeated reads identical.
- Viewer detail stayed 404 `dataset_not_found` even after an Analyst warmed the cache.
- All 22 successful analytical reads were 200 with `Cache-Control: no-store`; the
  only non-200 analytical outcome was the deliberate Viewer denial. No 429/503.
- Six HTTP-probe sessions logged out (204) and were rejected on reuse (401).
- Final check: zero unreleased query reservations; no query containers remained.

## Browser-visible timing

Fresh headless Chromium against Vite on 5173. Timing starts before the Sign in
click, so it includes login, `/me`, dashboard fetch and rendering. "Counters
settled" waits for the animated card to show the API percentage.

| Sample | Dashboard HTTP | Cards rendered | Counters settled | Facility list |
|---|---:|---:|---:|---:|
| Viewer desktop cold-looking | 6.761 s | 8.676 s | 9.515 s | n/a |
| Analyst desktop warm | 1.923 s | 3.745 s | 4.268 s | 5.553 s |
| Viewer mobile warm | 1.426 s | 2.920 s | 3.433 s | n/a |
| Analyst mobile warm | 1.482 s | 2.983 s | 3.550 s | 4.833 s |
| Admin desktop cold-looking | 5.800 s | 7.523 s | 7.923 s | 9.207 s |
| Admin desktop warm | 1.947 s | 3.866 s | 4.414 s | 5.697 s |

Login took ~0.86–1.57 s; the card counter animation added ~0.9 s. Analyst/Admin
contributions still follow the dashboard response, adding ~1.7–1.9 s.

The frontend changed concurrently (Explorer commits `6c9e780`, `4ad15d0` plus
local edits), so these are observations of that development frontend, not a
frozen build.

### Retained limitation — one Admin panel timeout

The first Admin browser run received a successful dashboard response (1.882 s)
and rendered cards (3.614 s), but the facility heading did not appear within 45 s.
Two isolated repeats passed and showed aborted development requests followed by
completed 200s. The cause is not established; no frontend correction was made.
Repeat on a fixed revision if it recurs.

## Reproduction

Scripts read the three existing `TRINITY_TEST_<ROLE>_PASSWORD` values; never place
real values in arguments or logs. Sessions are revoked in `finally`.

```bash
node scripts/measure_dashboard_http.mjs --phase before --output /permitted/tmp/before.json
node scripts/measure_dashboard_http.mjs --phase after --compare-to /permitted/tmp/before.json --output /permitted/tmp/after.json
node scripts/measure_dashboard_browser.mjs --output /permitted/tmp/browser.json
```

The `before` phase must run against the actual pre-rebuild API to be an uncached
baseline. Both scripts passed `node --check`; HTTP before/after passed; the first
browser campaign recorded the Admin timeout, both focused repeats passed.
`git diff --check` passed. No backend test was rerun: this continuation changed
measurement scripts and rebuilt already-tested sources.

## Outcome and next action

- Done: cache active in the retained API; full HTTP before/after, role/data/cleanup
  checks and browser milestone timings recorded.
- Remaining: cold HTTP reads still ~5.6–7.1 s; login, animation and the serial
  contributions request extend visible readiness.
- Open: the single non-reproduced Admin facility timeout.

Next action: [ME] Review these results and choose the next bounded cold-read
optimization. Cache values remain 60 seconds and 16 entries.
