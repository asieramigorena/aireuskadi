"""The materialized view core.unit_indicator, which every load has to refresh."""

from sqlalchemy import Engine, text


def refresh_unit_indicator(engine: Engine) -> None:
    """REFRESH ... CONCURRENTLY cannot run inside a transaction block, so call this after the
    commit of the load."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY core.unit_indicator"))
