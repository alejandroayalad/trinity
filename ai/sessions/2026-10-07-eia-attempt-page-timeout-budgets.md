# EIA attempt and page timeout budgets

References: A19 bounded retries, A23 timeout amendment, A16 publication safety.

[ME] Alayala supplied failed run 5, requested a direct EIA check, then selected
90 seconds per attempt within 150 seconds per page and requested the change.
[YOU] Changed only connector timeout handling and related tests/documentation.
Existing uncommitted recovery and documentation work remains preserved.

## Input, flow and output

An EIA page request retains the same route, dates, sort, offset and length.
`EIAClient._send_request` enforces a 90-second wall-clock attempt limit and maps
its expiry to the existing retryable `httpx.ReadTimeout`. HTTPX also uses
90-second I/O limits, retaining a 10-second connection limit. The enclosing
page timer is 150 seconds across requests, waits and response processing.
The unchanged route/supervisor deadlines can cancel work earlier. For example,
a first attempt lasting 90 seconds and a one-second wait leave 59 seconds for
the next attempt. Partial retrieval never becomes publication-ready.

The new regression cases prove a stalled attempt can time out and retry the
same page successfully; a 504 followed by a stalled retry still stops at the
shared page deadline; and constructed requests retain the selected I/O limits.
Tests use synthetic transport and scaled timers, without keys or live calls.

## Verification and deployment boundary

- Focused retry suite: 14 tests passed.
- All `test_eia_*.py`: 40 tests passed.
- Used the existing `backend/.venv/bin/python`; `uv` is unavailable on PATH.
- Retrieval suite: 16 tests passed. Preparation suite: 18 tests passed.
- Total across the three distinct suites: 74 passed; the 14 retry tests are
  already included in the 40 EIA tests. No skipped tests in these runs.
- Scoped implementation diff reviewed; `git diff --check` passed. Documentation
  references and the preserved parent deadlines were checked against source.
- No dependency, migration, production configuration or remote code changed.

The direct EIA check could not start through the existing browser terminal.
It stopped forwarding input; reconnecting returned `SendSSHPublicKey failed`.
No new live EIA result has been obtained. This does not establish that the API
is unavailable. Direct SSH with the existing key also timed out on port 22
with a six-second connection bound. No new API response or live completion is
claimed. No EC2 deployment, commit or push was performed.

Done: 90/150-second local change and 74 passing focused tests.
Pending: direct EIA probe and separately authorized EC2 deployment verification.
Blocker: EC2 management connection is unavailable.
Next: [ME] establish a working EC2 Instance Connect terminal.

## Direct EIA check after management access was restored

[ME] Opened a working Chrome Instance Connect terminal. [YOU] read run 5's
retained evidence, then made three direct HTTPS GET requests from the existing
refresh container at 20:24:40–20:24:41 UTC on October 7. The probe used a
90-second per-request deadline, no automatic retries, no redirects and no
environment proxy. It did not modify the worker or start a refresh.

Run 5 candidate `7fca30c3-a1a9-4a07-ba9e-dd4544d0cc9d` confirms facility
offset 40000 and generator offset 25000 were interrupted after approximately
30.02/30.03 seconds without HTTP responses. Both retained `request_deadline`.

The direct probe used `https://api.eia.gov/v2/nuclear-outages/`, the existing
`_ROUTES` paths, daily frequency, start `2024-10-02`, end `2026-10-07`, length
5000, all three measurement fields, and ascending full natural-key sorting.
These are the same window/offset/query parameters used by the failed pages.

| Dataset | Offset | HTTP | Rows in this page | Seconds |
| --- | ---: | ---: | ---: | ---: |
| national | 0 | 200 | 736 | 0.30 |
| facility | 40000 | 200 | 138 | 0.10 |
| generator | 25000 | 200 | 5000 | 0.22 |

All three JSON responses had data arrays and no API error field. These are
individual page probes, not full pagination, validation or publication proof.
They establish that the exact failed pages can succeed from EC2 with the current
credential. Intermittent external latency/failure is consistent with the earlier
deadlines and HTTP 504; its underlying cause remains unknown. The probes finished
below 30 seconds, so they do not establish that the timeout change is sufficient.

The credential was read only inside the container from the existing
`/run/secrets/eia_api_key` mount and sent only to the configured EIA endpoint.
No key value, response body or credential-bearing URL was printed or retained.
Two initial diagnostic invocations failed before making network requests:
`docker exec` does not inherit the entrypoint's exported key, and a settings
constructor used the field name instead of its uppercase input alias. Reading
the existing mounted secret directly corrected the diagnostic setup. These were
probe setup errors, not application credential failures.

Done: direct EIA check completed; 90/150-second code remains tested locally.
Pending: separately authorized EC2 deployment and full-refresh verification.
Blocker: none for management access in the restored terminal.

Final read-only deployed-source check still reports a 30.0-second page budget
and no separate attempt timer. The SHA256 remains
`4249966c1177c1dd1bb6820d4f9c305996a59f5500dd7f63168336812eea9739`.
The local timeout change has not reached EC2.

## Authorized EC2 deployment

[ME] Explicitly requested "deploy it". [YOU] verified no requested/running/
publishing refreshes before rollout; the latest run was 6 and already failed.
The host source matched the previously inspected deployed connector hash.
Existing untracked Compose/deployment files on EC2 were preserved.

A guarded transformation produced the exact tested connector bytes. An initial
staging command had a quoting syntax error before executing any mutations; the
corrected command passed both old/new SHA256 guards before creating the backup.
Backup: `/var/backups/trinity/eia-timeouts-20261007T202953Z/client.py`.
The same directory retains the old image ID, selected container identities/start
times and active publication pointer. Old image retained as
`trinity-api:before-eia-timeout-20261007`:
`sha256:66a294ace76d87557b34d104fcb56acccc282d1c5a009ae84ed6391532c042e6`.

Built one image layer over that exact deployed image, replacing only
`/opt/venv/lib/python3.14/site-packages/trinity/connector/client.py`. Build used
`--network=none --pull=false`; no dependency installation or unrelated source
change entered the image. New image `trinity-api:eia-timeout-20261007`:
`sha256:fa087724ef733b142951164fd477f7a004114bba5a1aa2c5d7b14a5b780ccb52`.
A disposable network-disabled, read-only container verified 90/150 constants,
exact source hash and successful retry after a synthetic stalled first request.

All five Compose layers validated with the retained `/etc/trinity/.env` and
`config --quiet`. Updated the host connector source to the same tested bytes,
tagged the new image `trinity-api:local`, and executed `up -d --no-deps --no-build
--wait --wait-timeout 30 refresh` for project `trinity-ec2`. The guarded rollout
included source/image rollback on replacement failure; rollback was not needed.
Only the refresh container was replaced. Other container IDs/start times and
the PostgreSQL active publication pointer were unchanged.

### Deployed verification

- Running worker started at `2026-10-07T20:31:05.042755344Z`, restart count 0.
- Imported live connector reports attempt 90.0 seconds and page 150.0 seconds.
- Live source SHA256 matches the tested local file:
  `b65853cb08de6f34eb22fb029b14cd5c4963b37ee4d9826ae808bd89a5db2735`.
- Public EC2 HTTPS returned 200. Unauthenticated Vercel `/api/v1/me` returned
  expected 401. These smoke checks establish ingress/auth availability only.
- Read-only SQL still showed latest run 6 and zero unfinished refreshes.

No refresh/recovery/publication command, Git commit or push was performed.
The earlier direct EIA probes used a separate diagnostic process before rollout;
full refresh completion with this deployed image remains unverified.

### Rollback reference

If rollback is authorized and the worker is idle, restore the saved `client.py`
to `backend/src/trinity/connector/client.py` in the EC2 checkout; tag the retained
old image as `trinity-api:local`; then recreate only `refresh` with the same
five Compose layers, environment file and project name. Verify old source hash,
worker status and unchanged publication pointer. Do not delete retained volumes.

Done: tested timeout change deployed and loaded limits verified on EC2.
Pending: one user-started full refresh to assess behavior under current EIA load.
Blocker: none observed for deployment.
Next: [ME] start one refresh from the application's Refresh page.

## Git delivery and image rebuilt from the pushed revision

[ME] Requested commit, push and retrieval of the image on EC2. [YOU] committed
only the timeout implementation/tests, selected README/NOTES paragraphs and
associated decision/evidence records as
`82a427bf14f4554b2cb68d50e48f8d91642e2c67` (`fix(refresh): separate EIA attempt and
page timeouts`). The normal push to `origin/main` also delivered the already
committed query-readability change `e646a6f`, announced before push. No history
was rewritten. Uncommitted recovery/frontend and documentation reconciliation
work remains local and was excluded from these commits.

The existing deployment uses local Docker images and has no configured image
publishing workflow. Fetched `origin/main` on EC2 and created a clean detached
checkout at `/home/ec2-user/trinity-releases/82a427b`; preserved the older live
checkout, its connector change and its untracked deployment files. Built with
the committed `backend/Dockerfile` and dependency lock, tagged
`trinity-api:82a427b`, with OCI revision label equal to the full commit ID.
Image ID:
`sha256:6c31d0dfd099dfc462e3d115fe333445dd1bdc4c1ddbc5c4abc39519d151afdd`.
This was a Git fetch and on-EC2 build, not a pull from a container registry.

Ran the committed `test_eia_client`, `test_eia_pagination`, `test_eia_retries`,
`test_retrieval` and `test_prepare` suites inside that exact image. The disposable
container used a read-only root/tests mount, writable `/tmp` tmpfs, no network,
no credentials, no capabilities and no new privileges. All 74 tests passed
in 32.413 seconds, with no skips.

After rechecking that no refresh was active, retained the prior patched image
as `trinity-api:before-release-82a427b`. Rollback metadata is saved on EC2 in
`/var/backups/trinity/release-82a427b/rollout.json`. Tagged the committed image
as `trinity-api:local` and recreated only `refresh` using the existing five
Compose layers and server environment. Other container identities/start times
and the active publication pointer were unchanged.

Final live inspection confirms revision `82a427b`, the expected image ID,
running status with zero restarts, the exact committed connector hash and
90/150-second limits. Public EC2 HTTPS returned 200 and unauthenticated Vercel
`/api/v1/me` returned expected 401. No full refresh was started in this delivery.

Done: code pushed to main; exact committed image built, tested and running on EC2.
Pending: a user-started full refresh remains the live EIA acceptance check.
Blocker: none observed. This delivery receipt is a separate documentation commit.
