# First live EIA run — October 3, 2026

**Result: passed.** The live gate and the three-route extraction both ran with alayala's EIA key. Exit code 0. No retries. The key does not appear in any output.

| Check | Result |
|---|---|
| Offline tests (CPython 3.14.8, uv 0.12.23) | 59/59 passed |
| Live gate `tests/live_eia.py -v` | 2/2 passed (~6 s) |
| Extraction for 2026-10-01, all routes | all `success`, EIA API 2.1.14, 2 pages each |

| Route | Rows returned | EIA advertised total |
|---|---:|---:|
| National | 1 | 1 |
| Facility | 55 | 95 (known [AN-03](../FINDINGS.md#an-03--the-facility-api-reports-more-rows-than-it-returns), accepted under A5/A9) |
| Generator | 95 | 95 |

Commands, run from `backend/` with `EIA_API_KEY` exported:

```bash
uv run --locked python -m unittest discover -s tests
uv run --locked python tests/live_eia.py -v
uv run --locked python -m trinity.connector --start 2026-10-01 --end 2026-10-01 --output <new-file>.jsonl
```

Notes:

- [YOU] AI ran these commands at alayala's explicit request. [ME] Alayala supplied the key.
- uv was not installed on the host. AI installed the pinned uv 0.12.23 in a temporary virtual environment. uv then downloaded CPython 3.14.8.
- The JSONL output was kept outside the repository and is not committed. Rerun the command to reproduce it.
- Not yet done: normalization, Parquet, full-window validation.
