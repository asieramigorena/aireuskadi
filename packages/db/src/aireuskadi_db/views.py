"""``unit_indicator``: materialized view with the impact indicators per municipality.

For each municipality, pollutant and year:
- declared_t: emissions declared by the facilities in the municipality (t/year)
- t_km2: declared_t divided by the municipality area
- who_ratio: mean annual concentration measured by its stations divided by the
  WHO annual guideline (latest edition); null when there is no station or guideline

The worker refreshes it after each load (REFRESH MATERIALIZED VIEW CONCURRENTLY).
"""

from sqlalchemy import Column, MetaData, Numeric, SmallInteger, String, Table

from aireuskadi_db.base import SCHEMA

UNIT_INDICATOR_DDL = f"""
CREATE MATERIALIZED VIEW IF NOT EXISTS {SCHEMA}.unit_indicator AS
WITH declared AS (
    SELECT f.municipality_code, fe.pollutant_code, fe.year,
           SUM(fe.amount_kg) / 1000 AS declared_t
    FROM {SCHEMA}.facility_emission fe
    JOIN {SCHEMA}.facility f ON f.id = fe.facility_id
    GROUP BY f.municipality_code, fe.pollutant_code, fe.year
),
measured AS (
    SELECT s.municipality_code, m.pollutant_code,
           EXTRACT(YEAR FROM m.ts AT TIME ZONE 'UTC')::smallint AS year,
           AVG(m.value) AS mean_ugm3
    FROM {SCHEMA}.measurement m
    JOIN {SCHEMA}.station s ON s.id = m.station_id
    GROUP BY s.municipality_code, m.pollutant_code, 3
),
guideline AS (
    SELECT DISTINCT ON (pollutant_code) pollutant_code, value_ugm3
    FROM {SCHEMA}.who_guideline
    WHERE averaging_period = 'annual'
    ORDER BY pollutant_code, edition DESC
)
SELECT mu.ine_code AS municipality_code,
       COALESCE(d.pollutant_code, me.pollutant_code) AS pollutant_code,
       COALESCE(d.year, me.year) AS year,
       COALESCE(d.declared_t, 0) AS declared_t,
       COALESCE(d.declared_t, 0) / NULLIF(mu.area_km2, 0) AS t_km2,
       me.mean_ugm3 / NULLIF(g.value_ugm3, 0) AS who_ratio
FROM declared d
FULL JOIN measured me
       ON me.municipality_code = d.municipality_code
      AND me.pollutant_code = d.pollutant_code
      AND me.year = d.year
JOIN {SCHEMA}.municipality mu
       ON mu.ine_code = COALESCE(d.municipality_code, me.municipality_code)
LEFT JOIN guideline g
       ON g.pollutant_code = COALESCE(d.pollutant_code, me.pollutant_code)
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS unit_indicator_pk
    ON {SCHEMA}.unit_indicator (municipality_code, pollutant_code, year);
"""

# Read-only table object for querying the view. It is kept out of Base.metadata
# so that metadata.create_all() does not try to create it as a table.
unit_indicator = Table(
    "unit_indicator",
    MetaData(schema=SCHEMA),
    Column("municipality_code", String(5), primary_key=True),
    Column("pollutant_code", String(20), primary_key=True),
    Column("year", SmallInteger, primary_key=True),
    Column("declared_t", Numeric),
    Column("t_km2", Numeric),
    Column("who_ratio", Numeric),
)
