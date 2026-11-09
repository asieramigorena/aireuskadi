"""The health check of the compose: is the service up, and can it reach its database?

It is not part of the public API: it is not in the OpenAPI document and the gateway does not route
it. The answer never says why it failed, because that would be the host, the user or the SQL.
"""

from http import HTTPStatus

from aireuskadi_http import problem
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from emissions_service.database import SessionDep

router = APIRouter()

HEALTH_PATH = "/health"


@router.get(HEALTH_PATH, include_in_schema=False)
def health(session: SessionDep):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return problem(HTTPStatus.SERVICE_UNAVAILABLE, "The service cannot reach the database.")
    return {"status": "ok"}
