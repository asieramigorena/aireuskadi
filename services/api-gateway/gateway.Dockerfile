# Image of the gateway, with the compiled web page inside. Build it with the repository root as
# context (the service needs packages/http, packages/logger and uv.lock, and the page needs
# web-client, which live outside this folder):
#   docker compose build api-gateway
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file with that exact name using its
# own folder as context, and a file called <name>.Dockerfile in a folder of services/ using the root
# of the repository as context, which is what this one needs.

# Stage 1: compile the web page (tsc checks the types, Vite makes web-client/dist).
# The base image by its digest: a tag can be published again.
# Security fix by Claude (audit 2026-11-26).
FROM node:22-slim@sha256:be979e5523c76fa4d5ca4ebd3099078f220aa47ec39c48ad5b5df9314debd6eb AS web
WORKDIR /web
COPY web-client/package.json web-client/package-lock.json ./
RUN npm ci
COPY web-client/ ./
RUN npm run build

# Stage 2: the gateway, which serves that page and the API. Node is not in this image.
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
COPY packages/db/pyproject.toml packages/db/pyproject.toml
COPY packages/http packages/http
COPY packages/logger packages/logger
COPY services/auth-service/pyproject.toml services/auth-service/pyproject.toml
COPY services/insight-service/pyproject.toml services/insight-service/pyproject.toml
COPY services/emissions-service/pyproject.toml services/emissions-service/pyproject.toml
COPY services/ingestion-worker/pyproject.toml services/ingestion-worker/pyproject.toml
COPY services/api-gateway/pyproject.toml services/api-gateway/pyproject.toml
COPY services/api-gateway/src services/api-gateway/src

RUN uv sync --frozen --no-dev --package api-gateway

COPY --from=web /web/dist /app/web
ENV WEB_DIR=/app/web

RUN useradd --system --no-create-home gateway
USER gateway

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# The request log comes from the application (JSON, without the query string or the headers).
# --no-server-header: the answers do not say which software is behind.
CMD ["uvicorn", "api_gateway.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
