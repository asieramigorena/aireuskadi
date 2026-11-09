"""Errors are application/problem+json (RFC 9457), in the answers and in the OpenAPI document."""

from aireuskadi_http import INVALID_REQUEST, NOT_FOUND, install_problem_documents
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException


def make_client():
    app = FastAPI()
    install_problem_documents(app)

    @app.get("/things", responses=INVALID_REQUEST)
    def things(year: int = Query(ge=1)):
        return []

    @app.get("/things/{code}", responses={**INVALID_REQUEST, **NOT_FOUND})
    def thing(code: str):
        raise StarletteHTTPException(404, f"Thing {code} not found.")

    return TestClient(app)


def test_an_unknown_path_is_a_problem_document():
    response = make_client().get("/no-such-path")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


def test_the_detail_that_a_route_gives_is_in_the_problem():
    response = make_client().get("/things/abc")

    assert response.status_code == 404
    assert response.json()["detail"] == "Thing abc not found."


def test_an_invalid_parameter_is_a_422_problem_that_names_it_and_does_not_echo_it():
    response = make_client().get("/things", params={"year": "<script>1"})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 422
    assert body["detail"] == "The request has invalid or missing parameters."
    assert [error["loc"] for error in body["errors"]] == [["query", "year"]]
    assert "<script>" not in response.text


def test_the_openapi_document_describes_the_errors_as_the_problem_documents():
    spec = make_client().get("/openapi.json").json()

    responses = spec["paths"]["/things/{code}"]["get"]["responses"]

    assert list(responses["404"]["content"]) == ["application/problem+json"]
    assert list(responses["422"]["content"]) == ["application/problem+json"]
    ref = responses["422"]["content"]["application/problem+json"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"type", "title", "status", "detail", "errors"}
    # FastAPI's own {"detail": [...]} shape is no longer in the document.
    assert "HTTPValidationError" not in spec["components"]["schemas"]
