# EC2 runtime configuration — prepared and validated

**Status: staged EC2 startup verified October 7, 2026. Accounts, API/Caddy and seven background services are running; public HTTPS is verified at https://54.224.94.9. Initial setup, real-data refresh/publication and query execution remain unverified.**
Audit date: October 6, 2026 (America/Merida). Source: current `ui/handoff-fidelity`
checkout, HEAD `0d77c5e`, including the uncommitted Caddy deployment files.
The direct instance-role AWS configuration is approved and verified as described
below. Staged startup is approved under A28. Configuration validation is not full
application acceptance.

## Audit table

`R` means runtime; `C` means Compose configuration before startup; `B` means image
build. Required means needed for the complete deployment requested here, even
when an API route loads the setting lazily rather than at process startup.
“Present, redacted” records presence only; no development secret was copied.
Internal service values are already in Compose and do **not** belong in `.env`.

### Database, queue and refresh

| Exact variable | Consuming service | Required/optional | Secret? | Expected format | Existing development value | Proposed EC2 value/source | Stage |
|---|---|---|---|---|---|---|---|
| `TRINITY_POSTGRES_PASSWORD` | Compose secret → PostgreSQL, API, all six workers, query recovery | Required | Yes | Nonempty password | Present, redacted | Generate a new EC2 password privately; retain it | C → R secret file |
| `TRINITY_DATABASE_URL` | API, scheduler, outbox, refresh, recovery, publication-outbox, publication, query recovery; migration/seed CLI | Required | Potentially; current DSN has no password | `postgresql://user@host:port/database` | Compose: `postgresql://trinity@postgres:5432/trinity`; native example has a password placeholder and port 15432 | Same Compose DSN, not the host loopback DSN | R, fixed |
| `TRINITY_POSTGRES_PASSWORD_FILE` | Backend image entrypoint in API/workers/query recovery | Required in this Compose setup; optional in native execution | No, path | Readable absolute file path | `/run/secrets/postgres_password` | Same; Compose supplies secret | R, fixed |
| `PGPASSWORD` | Psycopg/libpq in backend processes | Required here; entrypoint supplies it | Yes | Password bytes | Read from password file | Derived from secret file; do not duplicate in `.env` | R, derived |
| `POSTGRES_DB` | PostgreSQL image initialization | Required deployment identity | No | Database identifier | `trinity` | Same | R, fixed |
| `POSTGRES_USER` | PostgreSQL image initialization | Required deployment identity | No | Database role identifier | `trinity` | Same | R, fixed |
| `POSTGRES_PASSWORD_FILE` | PostgreSQL image initialization | Required here | No, path | Readable absolute file path | `/run/secrets/postgres_password` | Same | R, fixed |
| `POSTGRES_INITDB_ARGS` | PostgreSQL image initialization | Selected initialization option | No | `initdb` arguments | `--auth-host=scram-sha-256` | Same; only acts on an empty data directory | R, fixed |
| `TRINITY_REDIS_URL` | Outbox, refresh, recovery, publication-outbox, publication | Required for these five roles | Potentially; current URL has no password | Redis URL | `redis://redis:6379/0` | Same internal URL. Scheduler inherits but does not read it | R, fixed |
| `TRINITY_REFRESH_ROOT` | Refresh, recovery, publication-outbox, publication; publication-recover CLI | Required for custody roles | No | Existing absolute directory, UID/GID 10001, mode 0700 | `/var/lib/trinity/refresh` | Same, backed by `refresh_root`; initializer prepares ownership later | R, fixed |
| `TRINITY_WORKER_HOSTNAME` | Compose hostname for the four custody roles | Optional default; explicitly selected here | No | Stable common hostname | Default `trinity-worker` | `trinity-ec2-worker`; retain across restarts | C |
| `EIA_API_KEY` | Compose secret → refresh entrypoint → EIASettings | Required for refresh only | Yes | Nonblank EIA key | Present, redacted | Supply existing authorized key privately after approval | C → R |

The scheduler reads schedule/timezone/setup state from PostgreSQL. There are no
scheduler interval, timezone, queue-name, concurrency or worker-retry environment
variables in the current worker entrypoint. Redis uses command arguments, not a
`REDIS_PASSWORD` setting. Its persistence/authentication choices remain open in
`compose.yaml`; this proposal does not invent or silently set them.

### S3 and AWS identity

| Exact variable | Consuming service | Required/optional | Secret? | Expected format | Existing development value | Proposed EC2 value/source | Stage |
|---|---|---|---|---|---|---|---|
| `TRINITY_S3_BUCKET` | API query supervisor, refresh, recovery, publication | Required | No | Ordinary DNS S3 bucket name, not ARN/URL | `trinity-alayala-dev-01` | Same existing bucket, subject to IAM/access verification | C → R |
| `TRINITY_S3_PREFIX` | Same | Required | No | Safe nonempty relative path, ≤512 UTF-8 bytes | `private/candidates` | Same existing prefix | C → R |
| `TRINITY_S3_REGION` | Same | Required | No | AWS region string | `us-east-1` | Same; matches instance region | C → R |
| `TRINITY_S3_ENDPOINT_URL` | Refresh/recovery/publication S3Settings; not query reader | Optional; omit for AWS | No; credentials forbidden | HTTPS origin, no user info/query/fragment/non-root path | Omitted; backend example commented | Omit, not an empty assignment | R only if explicitly added to Compose |
| `TRINITY_QUERY_READ_PROFILE` | API `execution_factory` | Required; code explicitly creates a named Boto3 Session | No | AWS profile name present in config | `trinity-writer` | `trinity-reader`, backed directly by the attached instance role | C → R |
| `TRINITY_QUERY_AWS_DIRECTORY` | Compose bind source for API and EC2 custody workers | Required | No | Existing absolute directory containing `config` | `/Users/ALAYALA/.aws` | `/etc/trinity/aws`; mount only its non-secret `config` file | C |
| `AWS_PROFILE` | Refresh, recovery, publication SDK default session | Required for proposed writer selection | No | Profile name | `trinity-writer`, fixed in Compose | Same profile name; resolves attached instance-role credentials directly | R, fixed |
| `AWS_CONFIG_FILE` | API, refresh, recovery, publication SDK | Required with proposed mount | No | Readable config file path | API `/run/query-aws/config`; workers use default home config | `/run/trinity-aws/config` via EC2 override | R, fixed |
| `AWS_SHARED_CREDENTIALS_FILE` | Same SDKs | Explicit isolation setting | No | File path | API `/run/query-aws/credentials`; workers use default home file | `/dev/null`; no static credential file | R, fixed |
| `AWS_LOGIN_CACHE_DIRECTORY` | SDK local-login provider in original API configuration | Not used with EC2 IAM profiles | No | Cache directory if using AWS login | `/run/query-aws-login/cache` | Cleared to empty in override; login mount removed | R, fixed |
| `AWS_ACCESS_KEY_ID` | SDK credential chain if supplied | Not required; omit | Credential identifier; keep private | AWS access-key identifier | Not inspected or copied | Omit; temporary credentials resolved internally from IAM | R, absent |
| `AWS_SECRET_ACCESS_KEY` | SDK credential chain if supplied | Not required; omit | Yes | AWS secret access key | Not inspected or copied | Omit | R, absent |
| `AWS_SESSION_TOKEN` | SDK credential chain if supplied | Not required; omit | Yes | Temporary credential token | Not inspected or copied | Omit | R, absent |
| `HOME` | Base Compose's laptop AWS bind source; SDK home defaults | Base interpolation requires it; EC2 mount is replaced | No | Host home directory | `/Users/ALAYALA` | Normal invoking user's HOME; never overrides `/etc/trinity/aws/config` mount | C |

No `AWS_REGION` or `AWS_DEFAULT_REGION` variable is required: the S3 clients
receive `TRINITY_S3_REGION` explicitly and both profile sections specify their
region. No AWS key belongs in the web image, query container or build arguments.

### Query supervisor, query containers and signing keys

The query supervisor runs inside FastAPI; it is not an additional Compose
service. `query_recovery` is a separate trusted service. The supervisor creates
short-lived query containers dynamically.

| Exact variable | Consuming service | Required/optional | Secret? | Expected format | Existing development value | Proposed EC2 value/source | Stage |
|---|---|---|---|---|---|---|---|
| `TRINITY_QUERY_STAGE_ROOT` | API supervisor and query recovery | Required | No | Existing absolute non-symlink directory, private ownership | `/var/lib/trinity/queries` | Same, backed by `query_stage`; initializer prepares it later | R, fixed |
| `TRINITY_QUERY_STAGE_VOLUME` | API, query recovery, Compose volume | Required | No | Docker named-volume name | `trinity_query_stage` | `trinity_ec2_query_stage`; retain across restarts | C → R |
| `TRINITY_QUERY_DEPLOYMENT_ID` | API and query recovery | Required | No | UUID | `25c8f318-6aba-4aae-b733-e62f4cf14f91` | New stable `2ea64c0f-3e1a-49f0-95d8-caa5e1e06580` | C → R |
| `TRINITY_QUERY_IMAGE` | Supervisor, query recovery, query-stage initializer | Required | No | Immutable `sha256:` plus 64 lowercase hex characters; image must exist | `sha256:7618028421be473c7e37ba2558d899e5c98ad1113a44fb3e0a56d9bb2173e0be`, **linux/arm64** | **Unresolved**: build/transfer and inspect linux/amd64 query image later | C → R |
| `TRINITY_DOCKER_SOCKET` | API and query recovery Docker adapter | Required | No | Absolute Unix socket path inside container | `/var/run/docker.sock` | Same | R, fixed |
| `TRINITY_DOCKER_SOCKET_HOST` | Compose socket bind | Optional default | No | Existing host Unix socket path | `/var/run/docker.sock` | `/var/run/docker.sock` on EC2 | C |
| `TRINITY_DOCKER_GID` | Compose supplementary group for API/query recovery | Required | No | Numeric socket group ID | `0` | **993**, read from EC2 socket; recheck before startup | C |
| `TRINITY_PREVIEW_ENABLED` | FastAPI preview/dashboard/choice routes | Optional; default false | No | Only exact lowercase `true` enables | `true` | `true`, proposed; does not prove publication/query readiness | C → R |
| `TRINITY_PREVIEW_CURSOR_KEYS_JSON` | API preview cursor signer/verifier | Required for complete enabled frontend | Yes | JSON object with 1–4 unique key IDs, each mapped to 43-character unpadded base64url encoding of 32 bytes; ≤4096 bytes | Present, redacted | Generate independent new EC2 key; persist key ring | C → R |
| `TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID` | API preview signer | Required | No | Existing key ID, `[A-Za-z0-9_-]{1,32}` | `local1` | `ec2-preview-1` | C → R |
| `TRINITY_REFRESH_CURSOR_KEYS_JSON` | API refresh-list cursor signer/verifier | Required for complete Admin flow | Yes | Same key-ring format, separate key from preview | Present, redacted | Generate independent new EC2 key; persist key ring | C → R |
| `TRINITY_REFRESH_CURSOR_ACTIVE_KEY_ID` | API refresh-list signer | Required | No | Existing key ID, same ID format | `local1` | `ec2-refresh-1` | C → R |

Cursor keys currently enter the API as environment variables and are visible to
Docker administrators through inspect. The database and EIA credentials use
Compose secret files instead. Do not print an expanded Compose config or use
`config --environment` with the real file.

The dynamic query container receives only `PATH`, `PYTHONDONTWRITEBYTECODE` and
`PYTHONUNBUFFERED`. It has no network, credentials, AWS profile, database URL or
Docker socket. The trusted API stages authorized Parquet before execution.

### Web, authentication and build settings

| Exact variable | Consuming service | Required/optional | Secret? | Expected format | Existing development value | Proposed EC2 value/source | Stage |
|---|---|---|---|---|---|---|---|
| `COMPOSE_PROJECT_NAME` | Compose | Optional; explicit for stable resource naming | No | Compose project name | `trinity` | `trinity-ec2`; command also pins it | C |
| `COMPOSE_FILE` | Compose file selection | Optional; omitted here | No | Compose file list | `compose.yaml:compose.sql.yaml` | Omit; public deployment uses five explicit `-f` arguments | C |
| `TRINITY_RELEASE` | Compose web image tag | Optional default `local` | No | Existing image tag | `local` | `local`; retains existing `trinity-web:local` | C |
| `TRINITY_SITE_ADDRESS` | Compose → Caddy site label | Required | No | Caddy address | Template `http://:80` | `54.224.94.9`; trusted public IP HTTPS with the fifth Compose layer | C → R |
| `TRINITY_HTTP_BIND` | Compose web published port | Optional default | No | Host IP and port | `127.0.0.1:8080` | `0.0.0.0:80`; redirects and ACME challenges only | C |
| `TRINITY_HTTPS_BIND` | Compose web published port | Optional default | No | Host IP and port | `127.0.0.1:8443` | `0.0.0.0:443`; trusted public HTTPS | C |
| `TRINITY_API_TARGET` | Vite development/preview proxy only | Optional, not needed in production | No | HTTP API origin | Default `http://127.0.0.1:8000` | Omit; Caddy targets `api:8000` | Development server, not production runtime |
| `PATH` | Backend images; dynamic query container | Fixed image/process value | No | Colon-separated executable directories | Backend `/opt/venv/bin:$PATH`; query `/opt/venv/bin:/usr/bin:/bin` | Same; no `.env` entry | R, fixed |
| `PYTHONDONTWRITEBYTECODE` | Backend and query Python | Fixed | No | `1` | `1` | Same | R, fixed |
| `PYTHONUNBUFFERED` | Backend and query Python | Fixed | No | `1` | `1` | Same | R, fixed |
| `UV_COMPILE_BYTECODE` | Backend API Docker build stage | Fixed build optimization | No | `1` | `1` (API image only) | Same; no runtime input | B |
| `UV_LINK_MODE` | API and query Docker build stages | Fixed | No | uv link mode | `copy` | Same | B |
| `UV_PYTHON` | Same | Fixed | No | Python executable path | `/usr/local/bin/python3` | Same | B |
| `UV_PYTHON_DOWNLOADS` | Same | Fixed | No | uv download policy | `never` | Same | B |
| `UV_PROJECT_ENVIRONMENT` | Same | Fixed | No | Virtual environment path | `/opt/venv` | Same | B |

Authentication uses seeded local accounts and server-issued random bearer
sessions, stored in PostgreSQL with an eight-hour expiry. Passwords use salted
scrypt. There is **no JWT secret, session secret, Clerk key, cookie-domain or
CORS environment variable** to invent. Seed credentials are entered through
the existing hidden CLI prompts after migration; they are not `.env` inputs.
Frontend requests carry an Authorization header, not cookies.

`frontend/src/api/client.ts` builds relative `/api/v1...` URLs.
`frontend/Caddyfile` forwards `/api` and `/api/*` unchanged to `api:8000`.
`TRINITY_API_TARGET` only configures Vite's development/preview server. The web
Dockerfile has no public API URL build argument. **No endpoint-related rebuild
or public API URL is needed for the existing `trinity-web:local` image.** Its
observed EC2 image ID remains
`sha256:510ff1450e6d97ffaba15d12c76ae8cb11ac8dc99c44c694b8b153538287bcd3`.
This says nothing about whether later frontend source changes warrant a rebuild.

Test-only `TRINITY_TEST_*`, `TRINITY_PG_BIN` and `TRINITY_DOCKER_BIN` settings in
test runners/readmes are not runtime requirements. No backend/frontend `.env`
file is loaded automatically by the deployed Python settings or static bundle.

## Component coverage

| Component | Actual configuration inputs |
|---|---|
| FastAPI | Database/password file; query supervisor settings; both cursor rings; preview gate |
| PostgreSQL | Four `POSTGRES_*` variables above and password secret; persistent data volume |
| Redis | Internal URL consumed by clients; server flags `--maxmemory-policy noeviction`; no password/env contract |
| Scheduler | Database/password only; schedule comes from DB |
| Outbox | Database/password, Redis URL |
| Refresh | Database/password, Redis, refresh root/shared hostname, EIA secret, S3/writer profile |
| Recovery worker | Database/password, Redis, refresh root/shared hostname, S3/writer profile; no EIA |
| Publication outbox | Database/password, Redis, refresh root/shared hostname; no S3/EIA |
| Publication worker | Database/password, Redis, refresh root/shared hostname, S3/writer profile; exactly one instance |
| Query supervisor | API process: S3 reader, staging, immutable image, deployment ID, socket/group |
| Query recovery | Database/password, staging, image, deployment ID, socket/group; no S3 credentials |
| Query containers | Three fixed Python/process variables only; network disabled |
| Frontend/Caddy | Caddy site address plus Compose binds/image tag; static relative API requests |
| Initializers | Existing image, volume mount and fixed UID/GID/mode; no secrets |

## Approved EC2 AWS identity and live verification

Alayala attached `trinity-ec2-runtime` and approved using it directly for both
profiles. STS verified this identity from EC2 and the diagnostic container:
`arn:aws:sts::116645330977:assumed-role/trinity-ec2-runtime/i-0f7d31164bb1bedbe`.
The supplied `TrinityCandidateWriter` policy grants `s3:GetObject` and
`s3:PutObject` on `arn:aws:s3:::trinity-alayala-dev-01/private/candidates/*`.
The earlier additional `AssumeRole` call was denied and is no longer required.
No IAM policy or role trust was changed by the agent.

The approved [AWS profile file](../deploy/ec2/aws-config.example) contains only:

```ini
[profile trinity-reader]
region = us-east-1

[profile trinity-writer]
region = us-east-1
```

Installed on EC2 at `/etc/trinity/aws/config`, owner root:root, mode `0644`;
parent directories `/etc/trinity` and `/etc/trinity/aws` use `0700` and `0755`.
Docker mounts this file read-only at `/run/trinity-aws/config`. Both profiles
resolve temporary instance credentials in SDK memory; no static keys, credential
files, role ARN or `credential_source` setting are needed. Names preserve the
application's profile selection; they do not separate IAM permissions. Both the
trusted query supervisor and storage workers have the same S3 read/write scope.
This shared-role tradeoff is accepted under A28. Isolated query executors still
have no network, AWS credentials or Docker socket.

Live checks passed:

- Host: STS for both profiles, conditional `PutObject`, reader `GetObject` with
  exact byte comparison, and duplicate conditional write rejected with
  `PreconditionFailed`. The probe reports `AES256` encryption.
- Container: Python 3.14.8, Boto3/Botocore 1.43.108 and their locked SDK
  dependencies, UID/GID 10001, user-defined bridge network, read-only profile
  mount/root filesystem, dropped capabilities and no-new-privileges. SDK wheels
  were verified against `backend/uv.lock`; no application image was built.
- Both container profile paths (explicit reader Session and default Session with
  `AWS_PROFILE=trinity-writer`) used provider `iam-role` and returned the expected
  STS identity. Reading the host probe, creating a container probe, exact readback
  with both profiles and conditional duplicate rejection all passed.
- Host tokenless metadata returned HTTP 401. Container IMDSv2 token acquisition
  passed. EC2 denied `DescribeInstances`, so the numeric hop limit was not read;
  bridge-container metadata reachability was verified directly.

Two non-secret diagnostic objects remain, with no application registration or
publication. Existing objects were not changed and no deletes were attempted:

```text
private/candidates/_deployment_checks/9b5b1849-b225-45cf-9ba9-ac2a06047d92/host-probe.txt
private/candidates/_deployment_checks/ef2f6565-8f5f-4e34-a4b5-da96302a507c/container-probe.txt
```

Each contains 58 bytes of diagnostic text. These checks prove the sampled S3
operations and SDK/metadata path, not bucket-wide retention, lifecycle rules,
policy enforcement against unconditional writes or actual application startup.
At this initial check, the backend image was absent and the disposable
container/network were removed. Final-image verification now passed as recorded
in the October 7 staged rollout below.

[Boto3 credential resolution](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html),
[AWS metadata guidance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html)
and [conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
describe the provider and request behavior used by these checks.

## Installed EC2 .env — redacted view

The non-secret [template](../deploy/ec2/.env.example) deliberately leaves secret
values and the query image ID empty. The installed `/etc/trinity/.env` is now
complete. Alayala had already supplied seven entries on EC2: database password,
EIA key, query image ID and both cursor rings/active IDs. Completion preserved
all seven exactly and added the remaining reviewed settings. No secret was
rotated, copied from the laptop or printed. `REDACTED` below hides existing values;
it is not executable input. The file is root:root mode `0600`.

```dotenv
COMPOSE_PROJECT_NAME=trinity-ec2
TRINITY_RELEASE=local
TRINITY_SITE_ADDRESS=54.224.94.9
TRINITY_HTTP_BIND=0.0.0.0:80
TRINITY_HTTPS_BIND=0.0.0.0:443
TRINITY_POSTGRES_PASSWORD=REDACTED
EIA_API_KEY=REDACTED
TRINITY_S3_BUCKET=trinity-alayala-dev-01
TRINITY_S3_PREFIX=private/candidates
TRINITY_S3_REGION=us-east-1
TRINITY_WORKER_HOSTNAME=trinity-ec2-worker
TRINITY_QUERY_AWS_DIRECTORY=/etc/trinity/aws
TRINITY_QUERY_READ_PROFILE=trinity-reader
TRINITY_DOCKER_SOCKET_HOST=/var/run/docker.sock
TRINITY_DOCKER_GID=993
TRINITY_QUERY_STAGE_VOLUME=trinity_ec2_query_stage
TRINITY_QUERY_DEPLOYMENT_ID=2ea64c0f-3e1a-49f0-95d8-caa5e1e06580
TRINITY_QUERY_IMAGE=sha256:7ad87776b649db55c805d73363b8b9f736ac9520179706cda8c6821024c4b9fd
TRINITY_PREVIEW_ENABLED=true
TRINITY_PREVIEW_CURSOR_ACTIVE_KEY_ID=ec2-preview-1
TRINITY_PREVIEW_CURSOR_KEYS_JSON='{"ec2-preview-1":"REDACTED"}'
TRINITY_REFRESH_CURSOR_ACTIVE_KEY_ID=ec2-refresh-1
TRINITY_REFRESH_CURSOR_KEYS_JSON='{"ec2-refresh-1":"REDACTED"}'
```

Retain the supplied database password and cursor signing keys across restarts.
The EIA key is present; no EIA request was made to test it. Never paste these
values into chat or shell command history. Do not copy the development AWS directory or reuse the ARM64
query image hash. Preserve existing S3 objects; a new PostgreSQL database will
not automatically adopt existing publications merely because its bucket matches.

## Permissions and validation commands

The guarded first-install recipe below retains the initial installation history.
The installed public configuration requires `--public-https` for the validator and a fifth
`-f compose.public.yaml` for Compose. Use the exact current commands in
[public HTTPS deployment](deployment.md#public-https).

Original first-install recipe below, **not the procedure used for completion**.
The environment now exists; do not rerun this recipe to reset it. The guard
stops before overwriting existing configuration:

```sh
if sudo test -e /etc/trinity/.env; then
  echo 'Existing configuration requires review; stopping.'
  exit 1
fi
sudo install -d -o root -g root -m 0700 /etc/trinity
sudo install -d -o root -g root -m 0755 /etc/trinity/aws
sudo install -o root -g root -m 0600 deploy/ec2/.env.example /etc/trinity/.env
sudo install -o root -g root -m 0644 deploy/ec2/aws-config.example /etc/trinity/aws/config
```

The daemon binds the config **file**, not the parent directory. UID 10001 can
read this non-secret file inside containers. `/etc/trinity/.env` stays root-only.
Validation ran successfully from `/home/ec2-user/trinity-ec2` after completing
the file. Neither command creates or starts containers:

```sh
sudo python3 deploy/validate_ec2_env.py /etc/trinity/.env --public-https
sudo env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  docker compose --env-file /etc/trinity/.env --project-name trinity-ec2 \
  -f compose.yaml -f compose.sql.yaml -f compose.web.yaml -f compose.ec2.yaml \
  -f compose.public.yaml --profile workers config --quiet
```

The validator independently checks required secret sources because Compose
`config --quiet` alone does not establish that an environment-sourced secret is
nonempty. It reads all 21 distinct `${VARIABLE}` interpolations, ignores YAML
comments and escaped shell dollars, and rejects missing mandatory values.
Shell application variables and the checkout's development `.env` cannot fill
gaps. It also checks cursor/image/UUID formats and the merged AWS mounts/ports.

The first four files retain their order; `compose.ec2.yaml` removes the laptop
AWS mounts. `compose.public.yaml` comes last for this public deployment.
The validation commands above do not start services. Actual staged startup
and migration/seed results are recorded below.

Compose resolves environment-sourced secrets from its project environment,
which includes the explicit env file; shell export is not the only source.
See [Compose env-file handling](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
and [`resolveFileContent` in Compose 5.6](https://github.com/docker/compose/blob/v5.6.0/pkg/compose/secrets.go).
Do not run raw `config`, `config --environment` or verbose SDK logging with real secrets.

## Verification and remaining gates

**Initial audit evidence:** source audit; read-only EC2 role/credential-presence/socket/image checks;
all 21 interpolation inputs identified; draft validation returns exit 1 for
exactly five missing values. A separate synthetic fixture renders the merged
configuration and verifies that API/PostgreSQL/Redis have no published ports,
Caddy is loopback-only, and the four AWS-consuming services mount only the
read-only config file. Each of the five missing-value cases is rejected.
The synthetic merged check also passed on EC2 with Compose 5.6.0: 13 service
definitions, zero actual containers afterward, and the existing web image ID
unchanged. The backend's actual S3/API/EIA/cursor parsers accepted synthetic
values of the proposed shapes. The earlier local credential-provider check was
offline; the approved direct-role configuration now has the live host/container
SDK and S3 evidence above.
Synthetic credentials/image IDs are not an EC2 readiness result.

**October 7 completion:** the EC2 clone is `/home/ec2-user/trinity-ec2`, HEAD
`0d77c5e`. Its base Compose files and query Dockerfile match the reviewed local
sources. The clone lacked `deploy/`, `compose.web.yaml` and `compose.ec2.yaml`;
the required non-secret overlays, templates and validator were transferred.
`trinity-query:ec2` exists as linux/amd64 with the immutable ID above and the
expected `trinity.queries.runtime` command. This is image inspection, not query
execution or proof of its complete build provenance.

The environment completion preserved all seven existing entries, added missing
settings and wrote atomically only after successful validation. All 21 Compose
interpolation variables resolve. The validator and explicit four-layer Compose
`config --quiet` both exit 0. Cursor-key shapes and active IDs pass; static AWS
key variables are absent. At environment completion, zero containers and zero
volumes remained; no EIA call, migration, seed or image build had run.

**October 7 staged rollout:** Alayala authorized the backend build and sequential
infrastructure, migration/account, API/Caddy and worker gates. He explicitly
approved retaining PostgreSQL 17.11 for this deployment (A28).

The locked backend build on EC2 produced linux/amd64 `trinity-api:local`, ID
`sha256:66a294ace76d87557b34d104fcb56acccc282d1c5a009ae84ed6391532c042e6`,
from clone revision `0d77c5ed39ee1135fb283c9b9bcfb39ea91743c3`. A disposable
container using this final image passed Python 3.14.8/UID 10001 and API/worker
imports, both IAM-profile identities and exact S3 probe readback. A conditional
write to the existing diagnostic key returned PreconditionFailed and preserved
the object. The actual Docker constructor passed API `/v1.56` and immutable query
image lookup with socket GID 993. This is not full query execution proof.

Only PostgreSQL and Redis were started using an explicit service list and
`--no-deps --no-build --wait`. Both are healthy with no published host ports.
The backend image authenticated to PostgreSQL over the Compose network and
confirmed version 17.11 and zero pre-migration public tables. Redis 8.10.2 passed
PING, empty-keyspace and noeviction checks. Its observed default durability is
`appendonly=no`, `save=3600 1 300 100 60 10000`; no queue durability decision is
inferred from startup.

A root-only pre-migration dump was retained. `alembic upgrade head` exited 0;
post-migration checks match image head `0007_refresh_registration` and 20 public
tables. Accounts, refresh runs and job outbox are empty; setup is incomplete,
scheduling disabled and active publication null. Account passwords must be
entered through the existing hidden-input seed CLI before starting API/Caddy.
No EIA request, account seed, API/Caddy startup or worker startup ran.

**Account and application gate — October 7:** Alayala supplied a private password
note and authorized its use for all three accounts. The existing `seed_personas`
function received the value through an in-memory callback, using SSH standard
input rather than command arguments or a copied credential file. Three active
personas and their passwords were verified; hashes and credentials were not
printed or stored in project artifacts. The CLI and password rules were unchanged.

The staging initializer passed, followed by API health, both cursor rings,
private staging ownership and the full query-configuration constructor. Caddy
started separately. HTTP checks through Caddy passed for frontend assets, SPA
fallback, missing asset/API 404 and unauthenticated 401. All three personas passed
login, `/me`, role/landing checks, settings authorization, logout and revoked-token
401. Viewer/Analyst land on waiting; Admin lands on setup. These HTTP checks do
not establish browser visual acceptance or queries over published data.

Alayala approved AOF with `appendfsync everysec` and manual worker restarts.
The EC2 Redis override was installed after an empty-keyspace check, retaining
its prior config and data volume. A synthetic key survived a graceful restart;
only that diagnostic key was removed. Effective AOF/everysec/noeviction settings
passed. Abrupt-host-loss, restore and lost-delivery recovery remain untested.

After private refresh-root initialization, workers started and passed checks one
at a time: query_recovery, publication, publication-outbox, recovery, refresh,
outbox, scheduler. Each remained running without OOM, restart or logged error;
its effective database and applicable queue/storage configuration passed. These
workers have no Docker healthcheck, so process/dependency checks are not proof of
successful refresh, publication or crash recovery. No work was enqueued.

Final checks: 11 running containers; PostgreSQL, Redis and API healthy; no restart
counts; only Caddy ports bound to loopback. Three active accounts, no unrevoked
smoke-test sessions, disabled schedule, incomplete setup, no refresh/outbox/query
reservations or publication, and no queued/active/completed/failed jobs in either
BullMQ queue. The SSH tunnel on the laptop returned HTTP 200 at localhost:8080.

**Pending:** initial setup, authorized real refresh/publication, real query
execution/isolation, browser/operator acceptance and backups/restore. Initial public TLS passed in
the subsequent public-access gate; automatic renewal observation remains pending.
PostgreSQL 17.11, AOF everysec and manual worker restarts are explicitly approved
for this EC2 deployment. No full production acceptance is claimed.

## Public-access gate — October 7

Public HTTPS and HTTP308 passed with certificate verification enabled from the
laptop. Chrome opened the actual sign-in page without a certificate interstitial.
Let's Encrypt YE1 issued an IP SAN for 54.224.94.9, valid October7 05:32:39UTC to
October13 21:32:38UTC. The same retained Caddy image serves both origins; only
web was recreated. All three personas passed login, /me role, settings permission,
logout and revoked-token rejection over public HTTPS. Private SSH preview still
returns200. No frontend API URL or rebuild, secret rotation, IAM change or
security-group mutation was needed. Port80/443 rules were already present.

All21 interpolation names still resolve. Public preflight requires the fifth
layer, global IP, exact80/443/loopback8080 port mappings, and read-only Caddy
configuration mount. Negative checks reject plaintext site addresses, wrong TLS
ports, and public bindings in private mode. Future certificate renewal, stable
IP allocation and end-to-end data acceptance are separate from this issuance.

## Source trace

| Inspected source | What it establishes |
|---|---|
| `backend/src/trinity/config.py` — `EIASettings`, `ApiSettings`, `S3Settings` | Exact aliases, syntax, no automatic dotenv, optional endpoint behavior |
| `backend/src/trinity/workers/__main__.py` — `serve` | Per-role DB/Redis/EIA/S3/root inputs; scheduler branches before external settings |
| `backend/src/trinity/queries/config.py` — `execution_factory` | Explicit AWS read profile, immutable image, UUID, staging/socket contract |
| `backend/src/trinity/adapters/docker.py` — query create path | Only three executor environment variables; no network/credentials/socket |
| `backend/src/trinity/queries/cursors.py`, `refresh/cursors.py` | Exact signing key names, ring format and active key requirements |
| `backend/src/trinity/adapters/s3.py`, `queries/staging.py` | SDK storage clients, GetObject and conditional PutObject operations |
| `backend/src/trinity/auth/service.py`, `auth/repository.py`, seed CLI | Random DB sessions, eight-hour expiry, password hashing and hidden credential entry |
| `backend/src/trinity/main.py` | Exact `true` preview gate and lazy dependency behavior |
| `compose.yaml`, `compose.sql.yaml`, `compose.web.yaml`, proposed `compose.ec2.yaml` | Complete service environment, secret sources, interpolation, mounts, fixed settings |
| `backend/Dockerfile`, `backend/Dockerfile.query`, `backend/docker-entrypoint.sh` | Build-only uv variables, runtime Python flags, PGPASSWORD secret-file flow |
| `frontend/src/api/client.ts`, `frontend/vite.config.ts`, `frontend/Dockerfile`, `frontend/Caddyfile` | Relative URLs, development-only proxy target, runtime Caddy address |
| `backend/.env.example`, `deploy/.env.example`, backend/frontend README, `docs/deployment.md` | Existing documented inputs; small web template is not a full runtime template |

Runtime values in the table were rechecked against source/host observations;
prior local acceptance was not used as proof of this EC2 deployment.
