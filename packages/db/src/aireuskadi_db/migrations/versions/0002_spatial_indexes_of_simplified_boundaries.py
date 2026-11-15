"""The spatial indexes of the simplified boundaries, where they are missing.

The column geom_simplified was added by hand (ALTER TABLE) to the databases made before it existed,
and create_all() did not add its index to them. A database made by 0001 has them already: then this
does nothing.

Revision ID: 0002
Revises: 0001
Created: 2026-11-12
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ["territory", "district", "municipality"]


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_geom_simplified "
            f"ON core.{table} USING gist (geom_simplified)"
        )


def downgrade() -> None:
    # The indexes belong to 0001 in a database made by it: nothing to undo here.
    pass
