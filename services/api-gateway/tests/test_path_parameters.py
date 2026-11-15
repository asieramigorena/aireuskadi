"""The parts of the path that the browser chooses are checked before they are sent."""

import pytest

FACILITY_ID = "facility_id"
UNIT_CODE = "code"

# These reach the pattern of the route, and it refuses them.
NOT_A_CODE = [
    ("/api/v1/facilities/abc", FACILITY_ID),
    ("/api/v1/facilities/-1", FACILITY_ID),
    ("/api/v1/facilities/1.5", FACILITY_ID),
    ("/api/v1/facilities/12345678901", FACILITY_ID),
    ("/api/v1/facilities/%EF%BC%91", FACILITY_ID),  # a full-width 1
    ("/api/v1/facilities/1%0A", FACILITY_ID),
    ("/api/v1/facilities/%00", FACILITY_ID),
    ("/api/v1/facilities/%2e%2e", FACILITY_ID),  # `..`, which the client does not shorten
    ("/api/v1/units/ab", UNIT_CODE),
    ("/api/v1/units/1", UNIT_CODE),
    ("/api/v1/units/123", UNIT_CODE),
    ("/api/v1/units/123456", UNIT_CODE),
    ("/api/v1/units/0100a", UNIT_CODE),
    ("/api/v1/units/%EF%BC%91%EF%BC%92", UNIT_CODE),
    ("/api/v1/units/01%0A", UNIT_CODE),
    ("/api/v1/units/%00%00", UNIT_CODE),
    ("/api/v1/units/%2e%2e", UNIT_CODE),
]


@pytest.mark.parametrize(("path", "name"), NOT_A_CODE)
def test_a_code_that_cannot_be_the_one_of_something_is_a_422_before_it_is_sent(
    client, emissions, path, name
):
    response = client.get(path)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [e["loc"] for e in response.json()["errors"]] == [["path", name]]
    assert emissions.requests == []


# These do not reach the pattern: the client turns `..` into a shorter path before it sends it
# and a segment of the path cannot hold a `/`, so no route matches.
NO_ROUTE = [
    "/api/v1/facilities/..",
    "/api/v1/facilities/..%2Fhealth",
    "/api/v1/facilities/1%2F..%2Fhealth",
    "/api/v1/units/..",
    "/api/v1/units/..%2Fhealth",
    "/api/v1/units/01036%2F..%2Fhealth",
]


@pytest.mark.parametrize("path", NO_ROUTE)
def test_a_path_that_tries_to_climb_finds_no_route_and_is_not_sent(client, emissions, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert emissions.requests == []


@pytest.mark.parametrize("path", NO_ROUTE)
def test_a_path_that_climbs_to_the_health_check_never_gets_there(client, emissions, path):
    client.get(path)

    assert all(request.url.path != "/health" for request in emissions.requests)
