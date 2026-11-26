# AirEuskadi

How polluted is the air in each Basque town?

AirEuskadi is a web application that brings together open air pollution data of the Basque
Autonomous Community and shows it on a 3D map by municipality: the more pollution, the taller and
brighter the hexagonal column. It is a class project, and it is at an early stage.

It brings together:

- **Declared industrial emissions** (kg per year) of each facility, from the Basque E-PRTR register.
- **Measured air quality** (µg/m³) at each monitoring station, compared with the WHO 2021 guidelines.
- **Regional trend 1990-2024** by pollutant and sector, from the Basque emissions inventory (planned).

The unit of the map is the municipality (INE code). Districts and the three historical territories
add up their municipalities. The page is in Basque, Spanish and English: it follows the language of
the browser, and `?lang=eu|es|en` chooses one.

It is published at <https://aireuskadi.eus>.

## Run it locally

Requirements: Docker with Compose.

```sh
cp .env.example .env    # then set your own passwords and a JWT_SECRET (see below)
docker compose --profile worker up -d --build
```

That starts everything: PostgreSQL, Redis, the services, the gateway with the web page, the logs and
metrics (Loki, Alloy, Prometheus, Grafana) and the scheduler, which loads the data in its first
minute (boundaries, E-PRTR register, the last 48 hours of measurements and the inventory) and keeps it
up to date. The page and the API (`/api/v1/`) are on <http://127.0.0.1:8080> (`GATEWAY_PORT` of `.env`).

The database passwords go inside a URL, so use letters, digits, `-` and `_` only. One way to make
each password, and the `JWT_SECRET` (at least 32 characters), is:

```sh
openssl rand -base64 24 | tr '+/' '-_' | tr -d '='    # a password
openssl rand -base64 48 | tr '+/' '-_' | tr -d '='    # JWT_SECRET
```

### More or less

An admin account, for the panel at <http://127.0.0.1:8080/admin> (the accounts and Grafana; log in at
`/user`; name it like `GRAFANA_ADMIN_USER` of `.env`). Accounts made at `/user/signup` are never admins:
an admin is made here, or by another admin in the panel:

```sh
docker compose run --rm --entrypoint aireuskadi-admin db-init add <name>
docker compose run --rm --entrypoint aireuskadi-admin db-init promote <name>
```

Without the scheduler, and the loads one by one when you want them (the boundaries first):

```sh
docker compose up -d --build
docker compose run --rm --build ingestion-worker boundaries
docker compose run --rm --build ingestion-worker eprtr --year 2023
docker compose run --rm --build ingestion-worker measurements --hours 48
docker compose run --rm --build ingestion-worker inventory
```

Without the logs and metrics (about 500 MB of memory less): `docker compose up -d --build api-gateway`.

To work on the web page, with the stack running (needs Node.js 22 or later; it reloads on every
change, on <http://localhost:5173>): `cd web-client && npm ci && npm run dev`. The page on port 8080 is the
compiled one: `docker compose up -d --build api-gateway` shows the changes there.

To work on the Python code without containers (needs [uv](https://docs.astral.sh/uv/); put the
owner password in `DATABASE_URL` of `.env` too):

```sh
uv sync --all-packages
uv run --env-file .env aireuskadi-db-init
uv run --env-file .env python -m ingestion_worker.main boundaries
```

Anyone can sign up at <http://127.0.0.1:8080/user> and ask a language model about the data from the
panel of a municipality, with their own key (Groq, OpenRouter, Gemini, Mistral, Ollama, OpenAI): the
key stays in the tab and is never kept.

To show your own copy on the internet, `tunnel/` has a Tailscale Funnel that publishes only the
gateway. Put an auth key in `TS_AUTHKEY` of `.env` and run
`docker compose --profile tunnel up -d tunnel` (`docker compose stop tunnel` turns it off).

To stop it all: `docker compose --profile '*' down` (add `-v` to delete the data too).

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
