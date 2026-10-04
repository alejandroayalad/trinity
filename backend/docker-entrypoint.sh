#!/bin/sh
# Read the database password from the mounted secret so it is not part of
# TRINITY_DATABASE_URL or the container configuration. libpq reads PGPASSWORD.
set -eu
if [ -n "${TRINITY_POSTGRES_PASSWORD_FILE:-}" ]; then
    PGPASSWORD="$(cat "$TRINITY_POSTGRES_PASSWORD_FILE")"
    export PGPASSWORD
fi
exec "$@"
