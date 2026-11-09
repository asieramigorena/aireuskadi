# AirEuskadi

How polluted is the air in each Basque town?

AirEuskadi is a web application that brings together open air pollution data of the Basque
Autonomous Community and shows it on a 3D map by municipality: the more pollution, the taller and
brighter the hexagonal column. It is a class project, and it is at an early stage.

It brings together:

- **Declared industrial emissions** (kg per year) of each facility, from the Basque E-PRTR register.
- **Measured air quality** (µg/m³) at each monitoring station, compared with the WHO 2021 guidelines.
- **Regional trend 1990-2024** by pollutant and sector, from the Basque emissions inventory.

The unit of the map is the municipality (INE code). Districts and the three historical territories
add up their municipalities.

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 22 or later, Docker with Compose.

```sh
# Settings: copy the example and set your own passwords
cp .env.example .env

# Database and Redis
docker compose up -d --wait postgres redis

# Python components, the schema and the read-only role of the services
uv sync --all-packages
uv run --env-file .env aireuskadi-db-init

# Data: the boundaries first, then the E-PRTR register of one year and the last hours of
# measurements (all safe to repeat)
uv run --env-file .env python -m ingestion_worker.main boundaries
uv run --env-file .env python -m ingestion_worker.main eprtr --year 2023
uv run --env-file .env python -m ingestion_worker.main measurements --hours 48

# The rest of the services
docker compose up -d
```

The API is on <http://127.0.0.1:8080/api/v1/> (the gateway, `GATEWAY_PORT` of `.env`).
Grafana, with the logs and the state of the services, is on <http://127.0.0.1:3000> (user
`admin`, password `GRAFANA_ADMIN_PASSWORD` of `.env`).

## Credits

The data is open and published under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The Basque
Government (Eusko Jaurlaritza) asks to cite the source and not to alter the meaning of the data, see
its [legal notice](https://opendata.euskadi.eus/general/-/informacion-legal-opendata/).

| Source | Content |
| --- | --- |
| [Basque E-PRTR register](https://opendata.euskadi.eus/catalogo/-/registro-de-emisiones-y-transferencias-de-contaminantes-del-2023-prtr/), Open Data Euskadi | Emissions to air by facility and year |
| [Open Data Euskadi, air quality](https://opendata.euskadi.eus/) | Hourly measurements by station |
| Basque emissions inventory 1990-2024, Open Data Euskadi | Annual totals by pollutant and sector |
| [GeoEuskadi](https://www.geo.euskadi.eus/), Basque Government | Municipality, district and territory boundaries (simplified for the web map) |
| WHO global air quality guidelines 2021 | Reference values |

The Grafana stack (Loki, Alloy, Prometheus and Grafana, in `observability/` and the compose) was
set up assisted by Claude.

Licence: MIT. See [LICENSE](LICENSE).
