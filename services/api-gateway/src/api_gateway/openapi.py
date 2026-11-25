"""One documentation for the whole API, at /docs and /openapi.json (only when DOCS_ENABLED).

The list of routes is the gateway's own, so only what the gateway publishes is in it: never the
health check or an internal route of a service. Each route takes from its service what the
gateway does not know: the parameters and the shape of the answer.
"""

import copy
import re

import httpx
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html


def _same_route(path: str) -> str:
    """The route without the names of its parameters: the gateway says /stations/{station_id} and
    the service /stations/{id}, and both are the same route."""
    return re.sub(r"\{[^}]*\}", "{}", path)


async def _document_of(client: httpx.AsyncClient) -> dict | None:
    """The /openapi.json of a service, or None if it does not give it."""
    try:
        answer = await client.get("/openapi.json")
        answer.raise_for_status()
        return answer.json()
    except (httpx.HTTPError, ValueError):
        return None


def _merge(document: dict, services: list, prefix: str) -> None:
    """Puts into `document` what the services say of its routes."""
    operations = {}
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for service in services:
        if service is None:
            continue  # its routes keep the description of the gateway
        for path, item in service.get("paths", {}).items():
            operations[_same_route(path)] = item.get("get")
        schemas.update(service.get("components", {}).get("schemas", {}))

    for path, item in document["paths"].items():
        theirs = operations.get(_same_route(path.removeprefix(prefix)))
        if not theirs:
            continue
        ours = item["get"]  # every route of the gateway is a GET
        # The path parameters keep the names of the gateway; the others are the service's.
        parameters = [p for p in ours.get("parameters", []) if p["in"] == "path"]
        parameters += [p for p in theirs.get("parameters", []) if p["in"] != "path"]
        item["get"] = {**theirs, "parameters": parameters}
        if ours.get("description"):  # e.g. the card of a unit, which joins the two services
            item["get"]["description"] = ours["description"]


async def build_document(app: FastAPI, prefix: str) -> dict:
    services = [
        await _document_of(app.state.emissions),
        await _document_of(app.state.air_quality),
    ]
    # The gateway's own: its routes, without what they answer. A copy: FastAPI keeps the original.
    document = copy.deepcopy(app.openapi())
    try:
        _merge(document, services, prefix)
    except (AttributeError, KeyError, TypeError):
        # A document of a service that is not what OpenAPI says (a list, a field of another type):
        # no 500, the routes keep the description of the gateway.
        document = copy.deepcopy(app.openapi())
    return document


def install_docs(app: FastAPI, prefix: str) -> None:
    """The page and its document. The document is made each time it is asked for (two requests
    inside the compose), so it always says what the services say now."""

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_document():
        return await build_document(app, prefix)

    @app.get("/docs", include_in_schema=False)
    def docs_page():
        # Swagger UI loads its scripts from a CDN: that is why the page is only on when asked.
        return get_swagger_ui_html(openapi_url="/openapi.json", title="AirEuskadi API")
