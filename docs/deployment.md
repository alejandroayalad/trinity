# EC2 deployment: frontend and backend

The EC2 server runs both parts of Trinity. Caddy serves the compiled React/Vite
files and forwards `/api/v1/...` to FastAPI on the Compose network. Browsers use
one origin. No Vite development server or Node process runs in the web container.
The backend retains authentication, permissions, refresh/publication workers,
PostgreSQL, Redis and isolated query containers. See [A28](../DECISIONS.md#a28--ec2-web-deployment).

`compose.web.yaml` removes the API and PostgreSQL host ports. It adds only the
web image, retained certificate/config volumes and web restart policy. Worker
restart and custody rules remain those of A24; this is not a new recovery system.
The frontend image uses Node 24.21.0 for `npm ci` and the existing checked build,
then Caddy 2.11.7. There is no new npm or Python package. No existing HTTP server
was present; Caddy supplies static serving, reverse proxying and certificate
renewal in one image. Nginx plus separate certificate automation was the alternative.

The query supervisor requires Docker API **1.47 or newer**, with a compatible
minimum API version. The initial Amazon Linux package installed on EC2 is Docker
25.0.16 / API 1.44. After explicit upgrade approval, EC2 now runs the pinned
Docker 29.8.2 static daemon with observed API 1.56 / minimum 1.40. The original
Amazon packages, external containerd/runc, Compose, configuration and `overlay2`
image store were preserved. The actual constructor compatibility check passed;
real query execution/isolation checks remain pending before enabling analytics.
This static daemon needs deliberate security updates; DNF does not update it.
Do not lower `Docker.__init__`'s API check: the query mount uses volume subpaths.

## Private preview without a domain

Use an isolated checkout of one reviewed revision on EC2. Preserve ongoing local
UI work; do not deploy a changing directory or copy `.env`, AWS profiles or SSH
keys from the laptop. The new overlay is configuration, not a migrated database
or a complete working deployment.

Before startup, review the [complete runtime audit and proposed EC2 environment](ec2-runtime-configuration.md).
Use `deploy/ec2/.env.example` for the complete stack; `deploy/.env.example` contains
only the older web settings. The EC2 proposal replaces laptop AWS mounts with
the non-secret instance-role profile file and explicitly supplies all four
Compose layers. It leaves missing secrets and the AMD64 query image ID empty,
so validation fails until they are supplied. The attached instance role now passes host and isolated-container SDK/S3 checks.
The installed EC2 environment is now complete and passes both preflight checks.
The backend image and its IAM/query-constructor checks now pass. Staged startup has
completed through accounts, API/Caddy and sequential worker startup. Initial
setup and real-data acceptance remain pending. See the runtime audit for evidence
and limits.

After the separately approved configuration is installed, [YOU] validate it
from the reviewed checkout on EC2 without starting services:

```sh
sudo python3 deploy/validate_ec2_env.py /etc/trinity/.env
sudo env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  docker compose --env-file /etc/trinity/.env --project-name trinity-ec2 \
  -f compose.yaml -f compose.sql.yaml -f compose.web.yaml -f compose.ec2.yaml \
  --profile workers config --quiet
```

These commands validate configuration only. For the current EC2 rollout, the
backend build, migrations, accounts, API/Caddy and idle worker startup passed.
Initial setup and real-data/query verification remain later gates; follow
[backend setup](../backend/README.md) for their prerequisites. Keep the project
name and volume names stable. Build the query image from
`backend/Dockerfile.query` for linux/amd64 and use its actual inspected image ID.

If the EC2 user is not in the Docker group, use `sudo` with an explicitly supplied
server environment; ordinary `sudo` can drop required variables. Do not print
the rendered Compose configuration when it contains secrets. Validate with
`docker compose ... config --quiet` instead.

From the laptop, [ME] open the tunnel:

```sh
ssh -i ~/.ssh/trinity-ec2 -N -L 127.0.0.1:8080:127.0.0.1:8080 ec2-user@54.224.94.9
```

Open `http://localhost:8080`. HTTP stays on loopback; SSH encrypts the connection
between laptop and EC2. Keep web ports private in this mode. The IP is the current
instance address and can change after a stop/start. Public HTTPS is now available
through the additional layer below; the private tunnel remains an optional route.

## Public HTTPS

Current public URL: **https://54.224.94.9**. No SSH tunnel or domain is required.
The approved `compose.public.yaml` layer mounts `deploy/ec2/Caddyfile.public`
read-only over the image's private-preview configuration. It uses Let's Encrypt's
`shortlived` profile and sets default SNI for clients connecting directly by IP.
The existing web image and certificate volumes are retained; no frontend build.

Installed non-secret web settings in the protected EC2 environment:

```dotenv
TRINITY_SITE_ADDRESS=54.224.94.9
TRINITY_HTTP_BIND=0.0.0.0:80
TRINITY_HTTPS_BIND=0.0.0.0:443
```

Use all five files after enabling public mode. From the EC2 checkout:

```sh
sudo python3 deploy/validate_ec2_env.py /etc/trinity/.env --public-https
sudo env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root \
  docker compose --env-file /etc/trinity/.env --project-name trinity-ec2 \
  -f compose.yaml -f compose.sql.yaml -f compose.web.yaml -f compose.ec2.yaml \
  -f compose.public.yaml --profile workers config --quiet
```

The four-file private validator intentionally rejects these public bindings.
For an authorized web-only configuration change, append `up -d --no-deps
--no-build --wait web` instead of `config --quiet`; other services are untouched.

Public TCP80 redirects to HTTPS and supports certificate validation. TCP443
serves the frontend and relative `/api` requests. Only the private preview is
served over HTTP on host loopback8080 (container port8080). API/PostgreSQL/Redis
remain unpublished. The AWS console already showed public inbound TCP80/443;
no security-group or IAM change was made by this task.

Initial certificate issuance, external TLS verification, HTTP308, frontend
assets and all three role login/authorization/logout checks passed October7.
Caddy manages automatic renewal using retained `/data`; future renewal has not
yet been observed. IP certificates last 160hours. The current public IP can
change after EC2 stop/start; this is not a reserved address.

To return to private preview, restore the three values to `http://:80`,
`127.0.0.1:8080`, `127.0.0.1:8443`, validate without `--public-https`, and recreate
only web using the original four Compose files. Preserve all volumes and secrets.

Sources: [IP certificate availability](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability),
[Caddy TLS profile](https://caddyserver.com/docs/caddyfile/directives/tls),
[default SNI](https://caddyserver.com/docs/caddyfile/options#default-sni).

## Gates before calling the full deployment ready

1. Retain the compatible Docker API and verify isolated query execution.
   Configure unattended, separated S3 read/write permissions. The local Compose
   files mount interactive laptop AWS profiles; do not reuse that setup on EC2.
2. Apply reviewed migrations and seed retained accounts through the existing
   tools. Configure signing keys, EIA secret, query image/socket/staging and the
   shared refresh root. Keep secret values out of the frontend and Git.
3. Verify login, direct role denials, active publication, dashboard/SQL, a complete
   refresh and operator crash recovery on EC2. `/health` alone is insufficient.
4. Establish database/volume backups and restore proof. This EC2 deployment uses
   approved AOF everysec and manual worker restarts; preserve A24's stopped-worker
   proof. A graceful Redis restart check does not prove abrupt-loss recovery.
5. Initial public certificate, HTTP redirect and port checks passed; observe
   automatic renewal and keep the EC2 public address stable.

The API still ignores forwarded peer headers. Behind Caddy, login's per-peer
throttle groups clients by the proxy connection address. This preserves the
current security rule and is a shared-demo limitation; trusted client-IP handling
needs a separate reviewed change, not a blanket proxy-header switch.

Proxy routing follows [Caddy's SPA/API pattern](https://caddyserver.com/docs/caddyfile/patterns).
Measured checks and deployment boundaries belong in the
[implementation session](../ai/sessions/2026-10-06-ec2-caddy-web.md).
