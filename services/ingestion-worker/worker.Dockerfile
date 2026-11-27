# Image of the ingestion worker. Build it with the repository root as context (the worker needs
# packages/db, packages/http, packages/logger and uv.lock, which live outside this folder):
#   docker compose build ingestion-worker
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file with that exact name using its
# own folder as context, and a file called <name>.Dockerfile in a folder of services/ using the root
# of the repository as context, which is what this one needs.
# The base image by its digest: a tag can be published again.
# Security fix by Claude (audit 2026-11-26).
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

# uv by its digest too: it goes into every image. Security fix by Claude (audit 2026-11-26).
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The workspace needs the pyproject of every Python member, even if only one is installed.
COPY pyproject.toml uv.lock ./
COPY packages/db packages/db
COPY packages/http packages/http
COPY packages/logger packages/logger
COPY services/auth-service/pyproject.toml services/auth-service/pyproject.toml
COPY services/insight-service/pyproject.toml services/insight-service/pyproject.toml
COPY services/api-gateway/pyproject.toml services/api-gateway/pyproject.toml
COPY services/emissions-service/pyproject.toml services/emissions-service/pyproject.toml
COPY services/ingestion-worker services/ingestion-worker

RUN uv sync --frozen --no-dev --package ingestion-worker

COPY services/ingestion-worker/entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh

RUN useradd --system --no-create-home worker
USER worker

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["/app/entrypoint.sh"]
