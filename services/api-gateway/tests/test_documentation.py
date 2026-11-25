"""The documentation of the gateway: its public routes, described by the services behind them."""

import json

import httpx
import pytest
from api_gateway.main import create_app
from fastapi.testclient import TestClient

EMISSIONS_DOCUMENT = {
    "paths": {
        "/inventory": {
            "get": {
                "summary": "Inventory",
                "parameters": [{"name": "pollutant", "in": "query"}],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/InventoryOut"}
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {"schemas": {"InventoryOut": {"type": "object"}}},
}
AIR_QUALITY_DOCUMENT = {
    "paths": {
        # The service calls it `id`; the gateway, `station_id`.
        "/stations/{id}/measurements": {
            "get": {
                "summary": "Measurements",
                "parameters": [
                    {"name": "id", "in": "path"},
                    {"name": "pollutant", "in": "query"},
                ],
            }
        },
        "/units/{code}/stations": {"get": {"summary": "Internal"}},  # not published
    }
}


@pytest.fixture
def docs_client(upstreams, emissions, air_quality):
    emissions.respond(body=json.dumps(EMISSIONS_DOCUMENT).encode())
    air_quality.respond(body=json.dumps(AIR_QUALITY_DOCUMENT).encode())
    emissions_client, air_quality_client = upstreams
    with TestClient(create_app(emissions_client, air_quality=air_quality_client, docs=True)) as c:
        yield c


def test_each_public_route_has_the_description_of_its_service_and_nothing_else_is_there(
    docs_client,
):
    document = docs_client.get("/openapi.json").json()

    inventory = document["paths"]["/api/v1/inventory"]["get"]
    assert inventory["parameters"] == [{"name": "pollutant", "in": "query"}]
    answer = inventory["responses"]["200"]["content"]["application/json"]["schema"]
    assert answer == {"$ref": "#/components/schemas/InventoryOut"}
    assert "InventoryOut" in document["components"]["schemas"]
    # The path parameter keeps the name of the gateway, the query ones come from the service.
    measurements = document["paths"]["/api/v1/stations/{station_id}/measurements"]["get"]
    assert [p["name"] for p in measurements["parameters"]] == ["station_id", "pollutant"]
    # Only what the gateway publishes: no health check, no internal route of a service.
    assert all(path.startswith("/api/v1/") for path in document["paths"])
    assert "/api/v1/units/{code}/stations" not in document["paths"]
    assert docs_client.get("/docs").status_code == 200


def test_without_a_service_or_with_a_broken_document_the_routes_keep_the_gateway_description(
    docs_client, emissions, air_quality
):
    emissions.error = httpx.ConnectError("down")
    document = docs_client.get("/openapi.json").json()
    assert "parameters" not in document["paths"]["/api/v1/inventory"]["get"]
    assert "/api/v1/stations/{station_id}/measurements" in document["paths"]

    # A document that is JSON but not OpenAPI is no 500.
    air_quality.respond(body=b'{"paths": ["not", "a", "dict"]}')
    response = docs_client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/stations/{station_id}/measurements" in response.json()["paths"]
