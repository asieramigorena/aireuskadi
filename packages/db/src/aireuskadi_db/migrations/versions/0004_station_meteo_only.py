"""The stations that only send the weather (wind, humidity, pressure) and never a pollutant.

Revision ID: 0004
Revises: 0003
Created: 2026-11-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "station",
        sa.Column(
            "meteo_only",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="it only sends the weather, never a pollutant",
        ),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("station", "meteo_only", schema="core")
