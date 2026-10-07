# Refresh run 4: retained request deadlines

Mode: debugging. References: A16 lifecycle, A19 bounded external retries, A28 hosting.
[ME] Alayala supplied running/failed run 4 and successful run 1 screenshots and
asked how to debug failures through Vercel and EC2. [YOU] inspected local source
and used the existing EC2 Instance Connect terminal for read-only SQL and retained
retrieval metadata. No EIA calls, refresh/recovery commands, restarts or deployment
changes were made. Existing local changes were preserved.

## Confirmed operational finding

- Severity and scope: high for refresh availability; deployed EC2 retrieval.
- Expected: complete all three routes before preparation; retain the existing
  publication if retrieval is incomplete. Temporary requests can retry within
  the configured finite budget.
- Observed: run 4 (`b0ad6f3e-e9c3-4d2d-9a7f-70f049b703ac`) failed between
  20:03:26.267788 and 20:04:31.389265 UTC. Candidate
  `d1459a87-75f5-4870-8746-53b8ca42ac4a` retained national success (736 rows),
  facility failure (15,000 rows), and generator failure (10,000 rows).
- Evidence: read `refresh_runs` inside `BEGIN READ ONLY`, then selected metadata
  and attempt fields from each candidate's `evidence/retrieval.jsonl` in the
  refresh container. No response bodies or credentials were printed.
  Facility offsets 0/5000/10000 returned HTTP 200 in 0.36/0.35/0.28 seconds.
  Offset 15000 had no response and was interrupted at 30.03 seconds, with no retry.
  Generator offset 10000 returned HTTP 504 after 10.45 seconds; attempt 2 was
  interrupted after another 18.55 seconds. Both routes report `request_deadline`.
- Execution flow: `EIAClient._page` in `backend/src/trinity/connector/client.py`
  wraps `_request_with_retries` in a shared 30-second page deadline. The first
  retry waits one second. Thus 10.45 + 1 + 18.55 exhausts that page budget.
  `retrieve_all` retains each outcome; `prepare_candidate` in
  `backend/src/trinity/connector/pipeline.py` rejects incomplete retrieval before
  preparation and validation. `frontend/vercel.json` forwards API calls to the
  same EC2 origin; changing frontend entry point does not change this worker.
- Failure scenario: a page waits for the entire 30-second budget, or a 504 and
  subsequent attempt consume it. Remaining attempts cannot start after expiry;
  the run fails with partial counts retained only as evidence.
- Recommended correction: first reproduce a slow first request and a 504 followed
  by a slow retry using synthetic transport. Evaluate separate per-attempt and
  total page budgets while preserving finite route/stage limits and the maximum
  three attempts. This is a proposal, not an accepted policy or implemented fix.
- Validation still required: synthetic reproduction and reviewed retry policy;
  any resulting correction needs regression checks and an authorized deployed
  refresh. The evidence does not establish the underlying EIA/network latency
  cause or prove that a larger timeout would complete retrieval.

## Cross-checks and limits

The deployed client reports 30.0 seconds and retry delays (1.0, 3.0). Its SHA256
is `4249966c1177c1dd1bb6820d4f9c305996a59f5500dd7f63168336812eea9739`, identical
to the local inspected source. Run 3 also retained request deadlines; its facility
failed at offset 10000 after 30.03 seconds and generator at offset 5000 after
30.02 seconds. Run 1's retained routes all succeeded. The screenshots retain
publication `88c501f9`; the active pointer was not independently queried here.
Run 5 was already running when inspected; the agent did not start it or establish
its final result. Application tests were not run during this read-only diagnosis.

Done: run 4 cause confirmed from retained production evidence and matching source.
Pending: synthetic slow-request reproduction and bounded retry-policy review.
Blocker: underlying external latency cause remains unknown.
Next: [YOU] reproduce the slow-request deadline with a synthetic transport.
