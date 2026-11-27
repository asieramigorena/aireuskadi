# Official PostgreSQL image plus PostGIS from the PGDG repository, which the base image
# already configures and which publishes PostGIS for both amd64 and arm64.
# The base image by its digest: a tag can be published again.
# Security fix by Claude (audit 2026-11-26).
FROM postgres:17@sha256:97fb53376be3e4fb1a8a61421daa69dcc3bf2fa39bda3259f5245f9a455af1a9

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

# Runs once, when the data directory is created.
COPY init-postgis.sql /docker-entrypoint-initdb.d/10-postgis.sql
