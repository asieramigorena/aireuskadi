"""How Alembic reaches the database. `migrate()` (schema.py) gives it the connection; the command
line of Alembic (`uv run alembic -c packages/db/alembic.ini ...`) uses DATABASE_URL."""

import os

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine

from aireuskadi_db.base import Base
from aireuskadi_db.schema import include_object


def run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_schemas=True,
        include_object=include_object,
        # The columns of PostGIS are written as GeoAlchemy2 types, with their spatial indexes.
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with create_engine(os.environ["DATABASE_URL"]).connect() as conn:
        run(conn)
        conn.commit()
