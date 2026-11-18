"""A BRIN index on the time of the measurements.

The measurements grow every hour and are asked by time (the latest ones, a year, a range of days).
A BRIN index keeps the smallest and the largest time of each block of rows: it is tiny, and it is
enough because the rows are written in the order of their time.

Revision ID: 0005
Revises: 0004
Created: 2026-11-18
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS, like 0002: a database made from the models before the migrations has it.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_measurement_ts_brin ON core.measurement USING brin (ts)"
    )


def downgrade() -> None:
    op.drop_index("ix_measurement_ts_brin", table_name="measurement", schema="core")
