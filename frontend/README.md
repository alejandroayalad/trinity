# Trinity frontend

React, TypeScript and Vite implement the approved steps 3–9 on top of the
existing scaffold. See the [task record](../sdd/frontend/tasks.md) and
[implementation evidence](../ai/sessions/2026-10-05-frontend-steps-3-9-continuation.md).
Human visual acceptance and retained-system enablement remain separate.

For EC2 hosting of both frontend and backend, see
[Caddy deployment](../docs/deployment.md). The production web image serves the
compiled bundle; Vite remains the local development server.

## Vercel deployment preparation

Import the repository with Root Directory `frontend` and the Vite preset.
`vercel.json` selects `npm ci`, `npm run build`, and output directory `dist`.
It forwards `/api/*` unchanged to `https://54.224.94.9`, disables API response
caching, and supplies the React page fallback without rewriting missing
`/assets/*` files to HTML. No frontend API key or AWS credential is needed.

Select Node 24.x. Vercel manages the minor/patch release, so check the build log
against the repository's exact 24.21.0 pin; compatibility is not yet verified.
The EC2 address is currently unreserved. Update the rewrite if it changes.
This is local preparation, not a completed deployment or a replacement of A28.
After deployment, check login/logout, dashboard/SQL, a nested-page reload, a
missing asset (404), and an unauthenticated `/api/v1/me` (JSON 401, not HTML).
The existing EC2 deployment remains available.

## Run locally

Use Node.js **24.21.0** (`.nvmrc`). From this directory:

```sh
npm ci
npm run dev
```

Open the URL Vite prints. `/api` proxies to `http://127.0.0.1:8000` by default.
Start the [backend and provision local personas](../backend/README.md#local-api-and-three-personas)
first. Enter your own provisioned account and password. No password or EIA key
belongs in frontend configuration. `TRINITY_API_TARGET` overrides the proxy for
disposable tests. An absent publication produces the waiting state; this UI does
not activate query execution or publish a dataset.

## Verify

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

The build command also checks the bundle for forbidden prototype controls,
fixtures and test identities. Component tests replace HTTP and are offline evidence.

Browser checks use real loopback HTTP and their own native PostgreSQL 17.11
cluster. From `backend/`, after the locked environment and frontend packages exist:

```sh
uv run --locked python tests/run_local_auth_checks.py --frontend-browser
uv run --locked python tests/run_local_auth_checks.py --frontend-data
```

Install the pinned test browser first with `npx playwright install chromium`
from `frontend/`. The data command additionally requires a matching query image
and local Docker socket through `TRINITY_TEST_QUERY_IMAGE` (immutable `sha256:…`
ID) and `TRINITY_TEST_DOCKER_SOCKET`. Rebuild the existing backend query Dockerfile
when its runtime code changes. These tests use synthetic Parquet and synthetic
object storage with real isolated execution, never retained accounts or EIA.

The runner supplies generated persona credentials only to the test process
environment. Traces and videos are disabled. Selected data screenshots go to
ignored `test-results/`; they are examples, not Figma approval or data findings.
