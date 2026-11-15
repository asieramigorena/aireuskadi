# Image of the auth service (the accounts). Build it with the repository root as context (the
# service needs packages/db, packages/http, packages/logger and uv.lock, which live outside this
# folder):
#   docker compose build auth-service
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file with that exact name using its
# own folder as context, and a file called <name>.Dockerfile in a folder of services/ using the root
# of the repository as context, which is what this one needs.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The workspace needs the pyproject of every Python member, even if only one is installed.
COPY pyproject.toml uv.lock ./
COPY packages/db packages/db
COPY packages/http packages/http
COPY packages/logger packages/logger
COPY services/api-gateway/pyproject.toml services/api-gateway/pyproject.toml
COPY services/emissions-service/pyproject.toml services/emissions-service/pyproject.toml
COPY services/ingestion-worker/pyproject.toml services/ingestion-worker/pyproject.toml
COPY services/auth-service/pyproject.toml services/auth-service/pyproject.toml
COPY services/auth-service/src services/auth-service/src

RUN uv sync --frozen --no-dev --package auth-service

RUN useradd --system --no-create-home auth
USER auth

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# The request log comes from the application (JSON, without the query string or the body).
# --no-server-header: the answers do not say which software is behind. The compose publishes no
# port: only the gateway reaches it.
CMD ["uvicorn", "auth_service.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
