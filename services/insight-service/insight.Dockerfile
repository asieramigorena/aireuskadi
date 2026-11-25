# Image of the insight service (the questions to a language model). Build it with the repository
# root as context (the service needs packages/http, packages/logger and uv.lock, which live outside
# this folder):
#   docker compose build insight-service
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file called <name>.Dockerfile in a
# folder of services/ using the root of the repository as context, which is what this one needs.
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
COPY services/insight-service/pyproject.toml services/insight-service/pyproject.toml
COPY services/insight-service/src services/insight-service/src

RUN uv sync --frozen --no-dev --package insight-service

RUN useradd --system --uid 10010 --no-create-home insight
USER insight

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Nothing to configure: the provider, the model and the key of each person come with each question,
# and the key is never kept. --no-server-header: the answers do not say which software is behind. No port is published: only
# the gateway reaches it.
CMD ["uvicorn", "insight_service.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
