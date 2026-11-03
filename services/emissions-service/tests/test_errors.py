"""Errors are application/problem+json (RFC 9457), not FastAPI's default {"detail": ...}."""

import pytest


def test_an_unknown_path_is_a_problem_document(client):
    response = client.get("/no-such-path")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"year": 2023}, "pollutant"),
        ({"pollutant": "TSTP"}, "year"),
        ({"pollutant": "TSTP", "year": "last"}, "year"),
    ],
)
def test_a_missing_or_invalid_parameter_is_a_422_problem_that_names_it(client, params, field):
    response = client.get("/facilities/points", params=params)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 422
    assert body["type"] == "about:blank"
    assert [error["loc"][-1] for error in body["errors"]] == [field]


def test_the_invalid_value_is_not_echoed_back_in_the_problem(client):
    response = client.get("/facilities/points", params={"pollutant": "X", "year": "<script>1"})

    assert response.status_code == 422
    assert "<script>" not in response.text


def test_the_whole_422_problem_document_for_a_missing_parameter(client):
    response = client.get("/facilities/points", params={"pollutant": "TSTP"})

    body = response.json()
    # The phrase of status 422 changed name between Python versions.
    assert body.pop("title") in ("Unprocessable Entity", "Unprocessable Content")
    assert body == {
        "type": "about:blank",
        "status": 422,
        "detail": "The request has invalid or missing parameters.",
        "errors": [{"loc": ["query", "year"], "msg": "Field required", "type": "missing"}],
    }
