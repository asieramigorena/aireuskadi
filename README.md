# AirEuskadi

How polluted is the air in each Basque town?

AirEuskadi is a web application that brings together open air pollution data of the Basque
Autonomous Community and shows it on a 3D map by municipality: the more pollution, the taller and
brighter the hexagonal column. It is a class project, and the project is at an early stage: the
skeleton of every component exists, the application logic does not yet.

## What it shows

- **Declared industrial emissions** (kg per year) of each facility, from the Basque E-PRTR register.
- **Measured air quality** (µg/m³) at each monitoring station, from the Open Data Euskadi network,
  compared with the WHO 2021 guidelines.
- **Regional trend 1990-2024** by pollutant and sector, from the Basque emissions inventory.

The urban unit is the municipality (INE code). Districts and the three historical territories are
aggregations of municipalities. Emissions and concentrations are different quantities: they are
never summed, compared or stored in the same column.

The regional inventory only gives totals for the whole Basque Country, so the per-municipality map
uses the two sources that have a location: the facilities of the E-PRTR register and the air
quality stations.
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

The database has one schema, `core`, with the normalised model. `core.unit_indicator` is a
materialized view with the indicators of each municipality. The worker loads each file in a single
transaction, leaves out the rows that fail validation (logging each one with its reason) and
records every run in `core.ingestion_run`.

## Data sources

| Source | Content | Licence |
| --- | --- | --- |
| [Basque E-PRTR register](https://opendata.euskadi.eus/catalogo/-/registro-de-emisiones-y-transferencias-de-contaminantes-del-2023-prtr/) (Open Data Euskadi) | Emissions to air by facility and year, with coordinates | CC BY 4.0 |
| [Open Data Euskadi, air quality](https://opendata.euskadi.eus/) | Hourly measurements by station | CC BY 4.0 |
| Basque emissions inventory 1990-2024 | Annual totals by pollutant and sector | CC BY 4.0 |
| [GeoEuskadi](https://www.geo.euskadi.eus/) | Municipality, district and territory boundaries | CC BY 4.0 |
| WHO global air quality guidelines 2021 | Reference values | |

The Open Data Euskadi data is published by the Basque Government (Eusko Jaurlaritza) under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/), and its
[legal notice](https://opendata.euskadi.eus/general/-/informacion-legal-opendata/) asks to cite the
source, to give the date of the last update and not to alter the meaning of the data. The amounts
are loaded as published; when several rows share a facility and a pollutant, the largest is kept.

The national [PRTR-España](https://prtr-es.miteco.gob.es/) register is not used to load data. It
has no coordinates, and the layer that has them is behind an anti-robot check. It is kept as a
possible cross-check: its emissions files are public ZIPs per year.

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

# Load the data: the boundaries first, then the E-PRTR register of one year and the last hours
# of air quality measurements (all safe to repeat)
uv run --env-file .env python -m ingestion_worker.main boundaries
uv run --env-file .env python -m ingestion_worker.main eprtr --year 2023
uv run --env-file .env python -m ingestion_worker.main measurements --hours 48

# Node.js components
(cd services/air-quality-service && npm ci)
(cd web-client && npm ci)
```

The database listens on `127.0.0.1:5432` and Redis on `127.0.0.1:6379`. The tables are created
with `create_all()` and are not migrated: after changing the model, recreate the database with
`docker compose down -v`. The tests that use the database only run when `DATABASE_URL` is set; they
write rows of their own (municipality `99001`) and remove them.

The worker also runs in a container, which is the way its logs reach Loki and Grafana. Run these
from the root of the repository:

```sh
docker compose run --rm ingestion-worker boundaries
docker compose run --rm ingestion-worker eprtr --year 2023
docker compose run --rm ingestion-worker measurements
```

To keep the data up to date without launching the loads by hand, run the scheduler. It stays up and
runs the measurements every hour and the boundaries and the E-PRTR register every month (for the
register it also looks for a new year, which does not exist until the Basque Government publishes it):

```sh
docker compose --profile worker up -d ingestion-scheduler
```

The scheduler keeps no state of its own: it reads `core.ingestion_run` to know when each load last
succeeded, so a restart loses nothing and a stop of a few days is caught up (the measurements read
back far enough to cover the gap, up to a week). A load that fails is tried again after ten
minutes, not at its next turn, and one that fails does not stop the others. Instead of keeping a
process up you can ask for a single pass with `python -m ingestion_worker.main schedule --once`, for
example from a cron every five minutes: what is due is decided from `ingestion_run`, not from the
time of the cron.

It has a Dockerfile, `services/ingestion-worker/worker.Dockerfile`, built with the root of the
repository as context, and a compose entry in the profile `worker`, so `docker compose up` does not
start it. After a run the container stays up for `LOG_LINGER_SECONDS` seconds (20 by default) so
that Alloy has time to read its logs; set it to 0 if you do not look at the logs in Grafana. The other
application services have no Dockerfile yet, and `deploy-pro.yml` does not build this one.

Every run is recorded in `core.ingestion_run`, with the rows read, loaded and rejected, the hash of
the file and, for the E-PRTR register, the date of the last update that its catalog gives. Each
rejected row is logged with its line and the reason. A run loads in one transaction: if it fails,
nothing of it stays.

The worker (`services/ingestion-worker/src/ingestion_worker`) is organised by data source and by
general use: `boundaries/`, `eprtr/` and `measurements/` have one folder each, with the code that
reads the source, locates or checks it, loads it into `core` and runs the whole load; `common/` has
what every load shares (download, logs, the record of each run). The tests follow the same folders.

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

Logs and the state of the services. Every service writes JSON lines to standard output. Alloy sends
the logs of all the containers to Loki and their metrics (state, CPU, memory) to Prometheus, which
keeps them for seven days, and Grafana shows both. All of it starts with `docker compose up` and uses
about 500 MB of memory. The Grafana stack (Loki, Alloy, Prometheus and Grafana, in `observability/` and
the compose) was set up assisted by Claude.

Grafana is on <http://127.0.0.1:3000> (user `admin`, password `GRAFANA_ADMIN_PASSWORD` of `.env`)
with Loki and Prometheus already configured. In Explore, `{service="redis"}` shows the logs of a
service and `{service="ingestion-worker"} | json | level="WARNING"` filters by a field of the JSON
lines.

The folder `AirEuskadi` has four dashboards, loaded from `observability/dashboards/`: **Health**
(errors and log volume of every container), **Ingestion** (runs, rejected rows and errors of the
worker; it has data when the worker runs in a container, as above) and **Services** (which service is
up or down, since when, restarts, CPU and memory) and **API** (requests, errors and response time of
an API service, `emissions-service` by default, read from its JSON logs). To change one, edit its JSON file, because the
dashboards are read-only in Grafana.

The metrics come from the cAdvisor that is built into Alloy, which reads the cgroups, the Docker
socket and the containerd socket of the machine, all of them read only (`/sys`, `/var/lib/docker`,
`/var/run/docker.sock` and `/run/containerd/containerd.sock` in the compose). Docker 29 keeps its
containers in the containerd namespace `moby`; if your Docker keeps the containerd socket elsewhere,
change it in `docker-compose.yml` and `observability/alloy.alloy`. The traffic of the network of each
container is not shown: it needs the process namespace of the host. A service is "down" when it was
seen in the last hour and not in the last minute; the worker of the loads is left out because it only
runs on demand.

## Branches and deployment

- `dev`: work in progress. CI runs on every push.
- `pro`: deployed to the cloud. Images are published to GitHub Container Registry as
  `ghcr.io/asieramigorena/aireuskadi-<folder>:pro` for `linux/arm64`, and a server that pulls them
  (Watchtower) restarts the containers. Nothing connects to the server.
- `main`: releases. Each merge creates the next version tag and a GitHub release.

Only `dev` can be merged into `pro`, and both `pro` and `dev` into `main`. A pull request from `dev` into
`pro` is promoted by adding the label `promote` or commenting `/promote`: the workflow checks the
pull request and CI, publishes the images of its last commit and merges it.

## Status

The work is tracked in the issues. Done so far: the Python workspace and the data model, the local
database and Redis, the CI and deployment workflows, and the ingestion worker for the boundaries, the
E-PRTR register and the air quality measurements. Still empty: the FastAPI and Fastify apps and the
web client. The worker has its own scheduler. Next: the emissions inventory, and then expose the data
through the APIs and the map.

## Licence

MIT. See [LICENSE](LICENSE).
