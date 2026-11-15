"""The OpenAPI document is what the gateway merges: it has to describe the answers as they are."""


def test_the_422_of_a_route_with_parameters_is_described_as_the_problem_document(client):
    spec = client.get("/openapi.json").json()

    response_422 = spec["paths"]["/facilities/points"]["get"]["responses"]["422"]

    assert list(response_422["content"]) == ["application/problem+json"]
    ref = response_422["content"]["application/problem+json"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"type", "title", "status", "detail", "errors"}
    # FastAPI's own {"detail": [...]} shape is no longer in the document.
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_the_404_of_the_facility_card_is_described_as_the_problem_document(client):
    spec = client.get("/openapi.json").json()

    responses = spec["paths"]["/facilities/{facility_id}"]["get"]["responses"]

    assert list(responses["404"]["content"]) == ["application/problem+json"]
    ref = responses["404"]["content"]["application/problem+json"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"type", "title", "status", "detail"}
    # The 422 of the same route is still the validation problem.
    assert list(responses["422"]["content"]) == ["application/problem+json"]
