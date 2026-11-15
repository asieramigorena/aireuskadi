"""How the service connects: what a slow or failing query can cost, and what an error carries."""

import gc
from datetime import date

import pytest
from emissions_service.main import app_from_env, create_app
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError


@pytest.fixture
def service_engine(engine):
    """The engine that the service itself builds from DATABASE_URL."""
    return app_from_env().state.engine


def test_a_query_that_takes_more_than_five_seconds_is_cut(service_engine):
    with service_engine.connect() as conn:
        assert conn.execute(text("SHOW statement_timeout")).scalar() == "5s"


def test_a_database_error_does_not_carry_the_values_that_were_sent(service_engine):
    # The SQLAlchemy part of the message ("[parameters: ...]"). Some errors of PostgreSQL itself
    # repeat the value ("invalid input syntax ..."): those are avoided by validating the input.
    with pytest.raises(DBAPIError) as error, service_engine.connect() as conn:
        conn.execute(text("SELECT :value FROM core.no_such_table"), {"value": "SECRETVALUE"})

    assert "SECRETVALUE" not in str(error.value)


def test_the_pool_is_small_and_does_not_make_a_request_wait_for_long(service_engine):
    pool = service_engine.pool

    assert (pool.size(), pool.timeout()) == (5, 5)
    # No public way to read these two: the room above the pool and checking a connection is alive.
    assert (pool._max_overflow, pool._pre_ping) == (5, True)


def test_a_year_that_has_not_ended_is_refused_without_touching_the_database(engine):
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))

    response = TestClient(create_app(engine)).get(
        "/facilities/points", params={"pollutant": "NOX", "year": date.today().year}
    )

    assert response.status_code == 422
    assert statements == []


@pytest.mark.parametrize(
    "path",
    [
        "/pollutants",  # an answer
        "/facilities/2000000000",  # a 404 raised inside the route
        f"/facilities/points?pollutant=NOX&year={date.today().year}",  # a 422 raised inside it
        "/facilities/points?pollutant=NOX&year=2023",
    ],
)
def test_the_connection_of_a_request_is_given_back_whatever_the_answer(engine, path):
    gc.disable()  # otherwise the garbage collector would give a forgotten connection back
    try:
        TestClient(create_app(engine)).get(path)

        assert engine.pool.checkedout() == 0
    finally:
        gc.enable()
