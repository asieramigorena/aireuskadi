# AirEuskadi

How polluted is the air in each Basque town?

AirEuskadi is a web application that brings together open air pollution data of the Basque
Autonomous Community and shows it on a 3D map by municipality: the more pollution, the taller and
brighter the hexagonal column. It is a class project, and the project is at an early stage: the
skeleton of every component exists, the application logic does not yet.

## What it shows

- **Declared industrial emissions** (kg per year) of each facility, from PRTR-España.
- **Measured air quality** (µg/m³) at each monitoring station, from the Open Data Euskadi network,
  compared with the WHO 2021 guidelines.
- **Regional trend 1990-2024** by pollutant and sector, from the Basque emissions inventory.

The urban unit is the municipality (INE code). Districts and the three historical territories are
aggregations of municipalities. Emissions and concentrations are different quantities: they are
never summed, compared or stored in the same column.

The regional inventory only gives totals for the whole Basque Country, so the per-municipality map
uses the two sources that have a location: PRTR facilities and the air quality stations.
Administrative boundaries come from GeoEuskadi.

## Architecture

```text
SPA -> api-gateway -> emissions-service      -> PostgreSQL + PostGIS
                   -> air-quality-service    -> PostgreSQL + PostGIS
                   -> Redis (response cache)

ingestion-worker -> PostgreSQL + PostGIS   (the only writer)
```

The gateway is the only entry point and the only component that combines services; services never
call each other. Every API is REST with OpenAPI 3.x.

| Folder | What it is | Stack |
| --- | --- | --- |
| `web-client` | Single-page app with the 3D map | TypeScript (ES modules), Vite, deck.gl, MapLibre GL, Chart.js |
| `services/api-gateway` | Routing, composition, cache | Python, FastAPI, httpx, Redis |
| `services/emissions-service` | Emissions and inventory data | Python, FastAPI |
| `services/air-quality-service` | Air quality measurements | Node.js 22, TypeScript, Fastify |
| `services/ingestion-worker` | Downloads open data into the database | Python |
| `packages/db` | Data model shared by the Python components | SQLAlchemy 2, GeoAlchemy2 |
| `database` | PostgreSQL image with PostGIS (amd64 and arm64) | Docker |

The database has two schemas: `staging` (literal copy of what was downloaded) and `core` (the
normalised model). `core.unit_indicator` is a materialized view with the indicators of each
municipality.

## Data sources

| Source | Content | Licence |
| --- | --- | --- |
| [PRTR-España](https://prtr-es.miteco.gob.es/) | Emissions to air by facility and year | CC BY 4.0 |
| [Open Data Euskadi, air quality](https://opendata.euskadi.eus/) | Hourly measurements by station | CC BY 4.0 |
| Basque emissions inventory 1990-2024 | Annual totals by pollutant and sector | CC BY 4.0 |
| [GeoEuskadi](https://www.geo.euskadi.eus/) | Municipality, district and territory boundaries | CC BY 4.0 |
| WHO global air quality guidelines 2021 | Reference values | |

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 22 or later, Docker with Compose.

```sh
# Database and Redis
cp .env.example .env
docker compose up -d --wait

# Python components
uv sync --all-packages

# Create the core schema, its tables and the unit_indicator view (safe to repeat)
uv run --env-file .env aireuskadi-db-init

# Node.js components
(cd services/air-quality-service && npm ci)
(cd web-client && npm ci)
```

The database listens on `127.0.0.1:5432` and Redis on `127.0.0.1:6379`. The application services
have no Dockerfile or compose entry yet. The tables are created with `create_all()` and are not
migrated: after changing the model, recreate the database with `docker compose down -v`. The
database test in `packages/db` only runs when `DATABASE_URL` is set.

Checks that CI also runs:

```sh
uv run ruff check .
uv run pytest
(cd services/air-quality-service && npm run lint && npm run build)
(cd web-client && npm run lint && npm run build)
```

To block a commit that fails the linter, the tests or the secret scan, install the hooks once:

```sh
uv tool install pre-commit
pre-commit install
```

## Branches and deployment

- `dev`: work in progress. CI runs on every push.
- `pro`: deployed to the cloud. Images are published to GitHub Container Registry as
  `ghcr.io/asieramigorena/aireuskadi-<folder>:pro` for `linux/arm64`, and a server that pulls them
  (Watchtower) restarts the containers. Nothing connects to the server.
- `main`: releases. Each merge creates the next version tag and a GitHub release.

Only `dev` can be merged into `pro`, and only `pro` into `main`. A pull request from `dev` into
`pro` is promoted by adding the label `promote` or commenting `/promote`: the workflow checks the
pull request and CI, publishes the images of its last commit and merges it.

## Status

The work is tracked in the issues. Done so far: the Python workspace and the data model, empty
FastAPI and Fastify apps, an empty web client, the local database and Redis, and the CI and
deployment workflows. Next: create the tables, load one data source and expose it through the
APIs and the map.

## Licence

MIT. See [LICENSE](LICENSE).
