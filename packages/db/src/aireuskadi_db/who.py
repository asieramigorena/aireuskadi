"""WHO global air quality guidelines 2021: the reference values, as seed data.

Why they are written here by hand and are not loaded by the ingestion worker: the WHO does not
publish them as a file or an API that could be downloaded. They are ten figures in a table of a
report (Table 3.26 of the guidelines), and they change once in ten or fifteen years (2005, 2021).
There is nothing to fetch and nothing that changes between runs, so they are code, like the
pollutants of the worker (data/pollutants.csv) are data. When the WHO publishes a new edition, add
its values with a new `EDITION`: the view reads the latest one.

Every value is in ug/m3: the WHO publishes carbon monoxide in mg/m3 (4 mg/m3 over 24 hours), so it is
written here already converted (4000). The 2021 edition has no annual value for ozone, sulphur
dioxide and carbon monoxide, so `unit_indicator.who_ratio`, which divides by the annual one, is only
filled for PM2.5, PM10 and NO2.

Averaging periods: "annual", "24h", "8h" (the maximum daily 8-hour mean) and "peak_season" (the
average of those daily maxima over the six consecutive months with the highest ozone).
"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from aireuskadi_db.models import Pollutant, WhoGuideline

EDITION = 2021

# (pollutant code, averaging period, value in ug/m3)
GUIDELINES = [
    ("PM25", "annual", 5),
    ("PM25", "24h", 15),
    ("PM10", "annual", 15),
    ("PM10", "24h", 45),
    ("NO2", "annual", 10),
    ("NO2", "24h", 25),
    ("O3", "peak_season", 60),
    ("O3", "8h", 100),
    ("SO2", "24h", 40),
    ("CO", "24h", 4000),
]

# The pollutants that those guidelines are about, written the same as the ingestion worker writes
# them (data/pollutants.csv), so that the guidelines can be loaded before any data. The worker owns
# them: it updates their name and group, and this seed never overwrites an existing one. If you change
# a name there, change it here too.
POLLUTANTS = [
    ("PM25", "Particulate matter PM2.5", "particulate matter"),
    ("PM10", "Particulate matter PM10", "particulate matter"),
    ("NO2", "Nitrogen dioxide", "inorganic gas"),
    ("O3", "Ozone", "inorganic gas"),
    ("SO2", "Sulphur dioxide", "inorganic gas"),
    ("CO", "Carbon monoxide", "inorganic gas"),
]


def seed_who_guidelines(session: Session) -> None:
    """Writes the guidelines of 2021. It can be repeated: a value that was changed goes back to the
    published one. A pollutant that already exists is not touched (the worker owns its name)."""
    session.execute(
        insert(Pollutant)
        .values([{"code": c, "name": n, "group": g} for c, n, g in POLLUTANTS])
        .on_conflict_do_nothing(index_elements=["code"])
    )
    statement = insert(WhoGuideline).values(
        [
            {
                "pollutant_code": code,
                "averaging_period": period,
                "edition": EDITION,
                "value_ugm3": value,
            }
            for code, period, value in GUIDELINES
        ]
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["pollutant_code", "averaging_period", "edition"],
            set_={"value_ugm3": statement.excluded.value_ugm3},
        )
    )
