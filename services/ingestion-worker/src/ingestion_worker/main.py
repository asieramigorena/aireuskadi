"""Worker entry point. One loader per data source goes here."""

import logging

from ingestion_worker.logs import configure_logging

log = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    log.info("worker started")


if __name__ == "__main__":
    main()
