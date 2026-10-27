# Official PostgreSQL image plus PostGIS from the PGDG repository, which the base image
# already configures and which publishes PostGIS for both amd64 and arm64.
FROM postgres:17

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

# Runs once, when the data directory is created.
COPY init-postgis.sql /docker-entrypoint-initdb.d/10-postgis.sql
