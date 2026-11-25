"""Worker entry point.

    python -m ingestion_worker.main boundaries
    python -m ingestion_worker.main eprtr --year 2023
    python -m ingestion_worker.main measurements [--hours 48]
    python -m ingestion_worker.main inventory [--year 2024]
    python -m ingestion_worker.main schedule [--once]

The boundaries must be loaded first: the E-PRTR facilities and the stations are located on them.
"""

import argparse
import logging
import os
from collections.abc import Callable, Sequence
from datetime import date

from aireuskadi_logger import configure_logging
from sqlalchemy import Engine, create_engine

from ingestion_worker.boundaries.run import run_boundaries
from ingestion_worker.common.download import download
from ingestion_worker.eprtr.run import run_eprtr
from ingestion_worker.inventory.run import edition_exists, newest_edition, run_inventory
from ingestion_worker.jobs import default_jobs
from ingestion_worker.measurements.run import run_measurements
from ingestion_worker.scheduler import run_scheduler

log = logging.getLogger(__name__)


def main(
    argv: Sequence[str] | None = None,
    engine: Engine | None = None,
    fetch: Callable[[str], bytes] = download,
) -> None:
    configure_logging("ingestion_worker")
    parser = argparse.ArgumentParser(prog="ingestion-worker")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("boundaries", help="load the municipalities, districts and territories")
    eprtr = commands.add_parser("eprtr", help="load the emissions of the Basque E-PRTR register")
    eprtr.add_argument("--year", type=int, required=True, help="data year, e.g. 2023")
    measurements = commands.add_parser(
        "measurements", help="load the stations and the last hours of air quality measurements"
    )
    measurements.add_argument(
        "--hours", type=int, default=48, help="how many hours back to read (default 48)"
    )
    inventory = commands.add_parser(
        "inventory", help="load the inventory of emissions of the Basque Country by sector"
    )
    inventory.add_argument(
        "--year", type=int, help="edition, e.g. 2024 (default: the newest one published)"
    )
    schedule = commands.add_parser(
        "schedule",
        help="run the loads when they are due (measurements every hour, the rest monthly)",
    )
    schedule.add_argument(
        "--once", action="store_true", help="one pass, for a cron, instead of running for ever"
    )
    args = parser.parse_args(argv)

    if engine is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit(
                "DATABASE_URL is not set (copy .env.example to .env and use --env-file)"
            )
        engine = create_engine(url)
    log.info("worker started", extra={"command": args.command})
    if args.command == "boundaries":
        run_boundaries(engine, fetch=fetch)
    elif args.command == "eprtr":
        run_eprtr(engine, args.year, fetch=fetch)
    elif args.command == "measurements":
        run_measurements(engine, hours=args.hours, fetch=fetch)
    elif args.command == "inventory":
        year = args.year or newest_edition(edition_exists, date.today().year)
        if year is None:
            raise SystemExit("no edition of the inventory found in the last years")
        # By hand it always loads, also files that did not change: the job is the one that skips.
        run_inventory(engine, year, fetch=fetch, skip_unchanged=False)
    else:
        run_scheduler(engine, default_jobs(engine, fetch=fetch), once=args.once)
    log.info("worker finished", extra={"command": args.command})


if __name__ == "__main__":
    main()
