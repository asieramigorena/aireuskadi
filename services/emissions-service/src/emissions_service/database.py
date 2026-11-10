"""The database session of a request: one per request, closed when it ends."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def create_database_engine(url: str) -> Engine:
    """The engine of the service, built so that a request cannot cost much or leak much:
    - a query that takes more than 5 seconds is cut by the server;
    - the pool is small (5 connections and 5 more on a peak) and a request that finds none
      waits 5 seconds at most, instead of the 30 of the default;
    - a connection is tested before it is used, so a database that restarted does not fail the
      first request;
    - an error of the database does not carry the values that were sent in the query.
    """
    return create_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=5000"},
    )


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
