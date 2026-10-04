# Local API image. Credentials are supplied at runtime, never at build time.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

FROM python:3.14.8-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
# Install locked dependencies before the source so code edits reuse this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.8-slim-bookworm
RUN groupadd --system --gid 10001 trinity \
    && useradd --system --uid 10001 --gid trinity --no-create-home trinity
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER trinity
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
# The container binds all its interfaces; Compose publishes the port on loopback only.
CMD ["uvicorn", "trinity.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
