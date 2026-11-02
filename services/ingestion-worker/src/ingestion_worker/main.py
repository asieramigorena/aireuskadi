"""Worker entry point.

    python -m ingestion_worker.main boundaries
    python -m ingestion_worker.main eprtr --year 2023
    python -m ingestion_worker.main measurements [--hours 48]

The boundaries must be loaded first: the E-PRTR facilities and the stations are located on them.
"""

import argparse
import logging
import os
from collections.abc import Callable, Sequence

from sqlalchemy import Engine, create_engine

from ingestion_worker.boundaries.run import run_boundaries
from ingestion_worker.common.download import download
from ingestion_worker.common.logs import configure_logging
from ingestion_worker.eprtr.run import run_eprtr
from ingestion_worker.measurements.run import run_measurements

log = logging.getLogger(__name__)


def main(
    argv: Sequence[str] | None = None,
    engine: Engine | None = None,
    fetch: Callable[[str], bytes] = download,
) -> None:
    configure_logging()
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
    else:
        run_measurements(engine, hours=args.hours, fetch=fetch)
    log.info("worker finished", extra={"command": args.command})


if __name__ == "__main__":
    main()
