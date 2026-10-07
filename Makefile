# Local commands use the existing Compose project and private environment.
# Builds, migrations and account provisioning are explicit operator actions.
.DEFAULT_GOAL := help

BASE = docker compose -f compose.yaml
FULL = docker compose -f compose.yaml -f compose.sql.yaml --profile workers

.PHONY: help local-build local-up local-migrate local-seed local-install local-web local-health local-status local-stop query-build full-check full-up full-status full-stop

help:
	@printf '%s\n' \
	  'First setup (after exporting the PostgreSQL password):' \
	  '  make local-build     Build the API image' \
	  '  make local-up        Start PostgreSQL and API; wait for health' \
	  '  make local-migrate   Apply database migrations explicitly' \
	  '  make local-seed      Prompt privately for the three account passwords' \
	  '  make local-install   Install locked frontend dependencies' \
	  '  make local-web       Run Vite at http://127.0.0.1:5173 (foreground)' \
	  '' \
	  'Inspect or stop the base stack:' \
	  '  make local-health    Check API liveness at http://127.0.0.1:8000/health' \
	  '  make local-status    Show base service status' \
	  '  make local-stop      Stop base services; preserve named volumes' \
	  '' \
	  'Real data (configure storage, query runtime and workers in README first):' \
	  '  make query-build     Build the isolated query image' \
	  '  make full-check      Validate full Compose configuration quietly' \
	  '  make full-up         Validate and start the full backend, including scheduler' \
	  '  make full-status     Show full backend service status' \
	  '  make full-stop       Stop full backend; preserve named volumes'

local-build:
	$(BASE) build api

local-up:
	$(BASE) up -d --wait

# These commands use the API entrypoint to load the mounted database secret.
# Start the database first; neither target starts or rebuilds services implicitly.
local-migrate:
	$(BASE) run --rm --no-deps api alembic upgrade head

local-seed:
	$(BASE) run --rm --no-deps api python -m trinity.auth.seed

local-install:
	cd frontend && npm ci

local-web:
	cd frontend && npm run dev

local-health:
	curl --fail --silent --show-error http://127.0.0.1:8000/health

local-status:
	$(BASE) ps

local-stop:
	$(BASE) down

query-build:
	docker build -f backend/Dockerfile.query -t trinity-query:local backend

full-check:
	$(FULL) config --quiet

# Validation precedes startup even with make -j. An enabled saved schedule can
# start live work as soon as the scheduler starts; this is not a preview command.
full-up: full-check
	$(FULL) up -d --wait

full-status:
	$(FULL) ps

full-stop:
	$(FULL) down
