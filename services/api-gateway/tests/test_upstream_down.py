"""When the emissions service cannot be reached, the browser gets a fixed answer."""

import httpx
import pytest

URL = "/api/v1/units?level=municipality&pollutant=NOX&year=2023"


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("[Errno -2] Name or service not known: emissions-service"),
        httpx.RemoteProtocolError("server disconnected"),
    ],
)
def test_a_service_that_cannot_be_reached_is_a_502_without_its_name_or_its_port(
    client, emissions, error
):
    emissions.error = error

    response = client.get(URL)

    assert response.status_code == 502
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The service is not available."
    assert "emissions" not in response.text
    assert "8000" not in response.text


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("timed out"), httpx.ConnectTimeout("connect to emissions-service:8000")],
)
def test_a_service_that_takes_too_long_is_a_504_without_its_name_or_its_port(
    client, emissions, error
):
    emissions.error = error

    response = client.get(URL)

    assert response.status_code == 504
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The service did not answer in time."
    assert "emissions" not in response.text
    assert "8000" not in response.text
