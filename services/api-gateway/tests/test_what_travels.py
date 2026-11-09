"""What the gateway sends to the emissions service, and what it gives back to the browser."""

import pytest

URL = "/api/v1/units?level=municipality&pollutant=NOX&year=2023"


def test_the_parameters_that_are_not_in_the_list_of_the_route_are_dropped(client, emissions):
    client.get(URL + "&admin=1&debug=true&year=2022")

    (sent,) = emissions.requests
    assert set(sent.url.params) == {"level", "pollutant", "year"}
    assert "admin" not in str(sent.url)


def test_a_parameter_that_comes_twice_is_sent_twice_and_the_service_decides(client, emissions):
    client.get("/api/v1/units?level=municipality&pollutant=NOX&year=2023&year=2022")

    (sent,) = emissions.requests
    assert sent.url.params.get_list("year") == ["2023", "2022"]


def test_the_values_of_the_parameters_cannot_change_the_path_that_is_asked(client, emissions):
    client.get("/api/v1/units?level=../health&pollutant=%2e%2e%2fhealth&year=1")

    (sent,) = emissions.requests
    assert sent.url.path == "/units"


def test_the_headers_of_the_browser_do_not_reach_the_service(client, emissions):
    client.get(
        URL,
        headers={
            "Authorization": "Bearer secret-token",
            "Cookie": "session=abc",
            "X-Forwarded-For": "6.6.6.6",
            "X-Forwarded-Host": "evil.example",
            "X-Real-IP": "6.6.6.6",
            "Forwarded": "for=6.6.6.6",
            "X-Api-Key": "k",
            "Referer": "http://evil.example/",
            "Origin": "http://evil.example",
        },
    )

    (sent,) = emissions.requests
    names = {name.lower() for name in sent.headers}
    assert names <= {"host", "accept", "accept-encoding", "connection", "user-agent"}, names
    assert sent.headers["host"] == "emissions.internal:8000"  # set by the gateway, not the client


@pytest.mark.parametrize(
    ("status", "content_type", "body"),
    [
        (404, "application/problem+json", b'{"status": 404, "detail": "Unit 99999 not found."}'),
        (422, "application/problem+json", b'{"status": 422, "errors": []}'),
    ],
)
def test_the_errors_of_the_service_come_back_as_they_are(
    client, emissions, status, content_type, body
):
    emissions.respond(status, body, content_type)

    response = client.get(URL)

    assert response.status_code == status
    assert response.headers["content-type"] == content_type
    assert response.content == body


def test_only_the_content_type_of_the_answer_comes_back_not_the_headers_of_the_service(
    client, emissions
):
    emissions.respond(
        headers={
            "X-Internal-Host": "emissions-service:8000",
            "Server": "uvicorn",
            "Set-Cookie": "a=b",
        }
    )

    response = client.get(URL)

    names = {name.lower() for name in response.headers}
    assert "x-internal-host" not in names
    assert "server" not in names
    assert "set-cookie" not in names
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, b"Internal Server Error"),
        (503, b'{"detail": "cannot reach the database"}'),
        (302, b""),
    ],
)
def test_a_failure_of_the_service_is_a_502_that_says_nothing_of_the_reason(
    client, emissions, status, body
):
    emissions.respond(
        status, body, "text/plain", headers={"Location": "http://emissions-service/x"}
    )

    response = client.get(URL, follow_redirects=False)

    assert response.status_code == 502
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "The service is not available."
    assert "database" not in response.text
    assert "location" not in response.headers
