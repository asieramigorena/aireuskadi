"""Errors as application/problem+json (RFC 9457), and how the OpenAPI document describes them."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class Problem(BaseModel):
    """application/problem+json (RFC 9457) answer for an error."""

    type: str
    title: str
    status: int
    detail: str


class ValidationErrorOut(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationProblem(Problem):
    """The answer for a request with invalid parameters: the problem and what is wrong."""

    errors: list[ValidationErrorOut]


# For the routes that take parameters (or look something up): describes the 422 (and the 404)
# as sent, instead of FastAPI's own {"detail": [...]}, which is what the OpenAPI document would
# say otherwise.
INVALID_REQUEST = {422: {"model": ValidationProblem}}
NOT_FOUND = {404: {"model": Problem}}


def problem(status: HTTPStatus, detail: str, **extra) -> JSONResponse:
    """An error as application/problem+json (RFC 9457); `extra` adds members to the document."""
    return JSONResponse(
        {
            "type": "about:blank",
            "title": status.phrase,
            "status": status.value,
            "detail": detail,
            **extra,
        },
        status_code=status.value,
        media_type="application/problem+json",
    )


def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    return problem(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "The request has invalid or missing parameters.",
        errors=[
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()
        ],
    )


def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    return problem(HTTPStatus(error.status_code), error.detail)


def install_problem_documents(app: FastAPI) -> None:
    """Make every error of the application a problem document, in the answers and in the
    OpenAPI document."""
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(StarletteHTTPException, http_error)

    generate_openapi = app.openapi

    def openapi() -> dict:
        """FastAPI describes a response model as application/json: the problem documents are
        sent as application/problem+json, so that is how they are described."""
        spec = generate_openapi()
        for path in spec["paths"].values():
            for operation in path.values():
                for status in ("404", "422"):
                    content = operation["responses"].get(status, {}).get("content", {})
                    if "application/json" in content:
                        content["application/problem+json"] = content.pop("application/json")
        return spec

    app.openapi = openapi
