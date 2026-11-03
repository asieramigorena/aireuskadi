"""Errors are application/problem+json (RFC 9457), not FastAPI's default {"detail": ...}."""


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
