"""The read-only role of the services that only read (the emissions API, and later the gateway
and the air quality API).

The owner of the database can write, drop tables and read the record of every load. A service that
only answers questions has no use for any of that, so it connects with this role instead: it can
read the tables that are served and nothing else, and what it reads is capped (a query is cut after
5 seconds, at most 10 connections). If the service is ever broken into, that is all it can do.

``create_reader_role`` is safe to run again: it creates the role if it is missing, and every time
it sets the password and puts the privileges back as they have to be. Run it with the owner.
"""

import re

from psycopg import sql
from sqlalchemy import Engine, text

from aireuskadi_db.base import SCHEMA, Base

# The record of the loads (source URLs, file hashes, error texts) is for the worker alone.
NOT_SERVED = {"ingestion_run"}

# Lower case, digits and underscore, at most the 63 bytes of a PostgreSQL name.
_ROLE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def create_reader_role(engine: Engine, user: str, password: str) -> None:
    if not _ROLE_NAME.fullmatch(user):
        raise ValueError(f"{user!r} is not a plain role name (lower case, digits and underscore)")
    if not password:
        raise ValueError("The password of the role is empty")

    served = sorted(
        [t.name for t in Base.metadata.tables.values() if t.name not in NOT_SERVED]
        + ["unit_indicator"]  # the materialized view, which is not in the metadata as a table
    )
    role = sql.Identifier(user)
    with engine.begin() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": user})
        database = conn.scalar(text("SELECT current_database()"))
        statements = [] if exists else [sql.SQL("CREATE ROLE {}").format(role)]
        statements += [
            sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                "NOBYPASSRLS CONNECTION LIMIT 10 PASSWORD {}"
            ).format(role, sql.Literal(password)),
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role),
            sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role),
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), role),
            # Start from nothing, so that running it again also removes what was granted by hand.
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
                sql.Identifier(SCHEMA), role
            ),
            sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(sql.Identifier(SCHEMA), role),
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(SCHEMA), role),
            sql.SQL("GRANT SELECT ON {} TO {}").format(
                sql.SQL(", ").join(sql.Identifier(SCHEMA, name) for name in served), role
            ),
        ]
        cursor = conn.connection.driver_connection.cursor()
        for statement in statements:
            cursor.execute(statement)
