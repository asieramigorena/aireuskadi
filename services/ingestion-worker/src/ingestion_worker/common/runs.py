"""Records a run of a loader in core.ingestion_run."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from aireuskadi_db import IngestionRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def track_run(
    engine: Engine,
    source: str,
    url: str,
    work: Callable[[Session, IngestionRun], None],
) -> None:
    """Opens the run, calls work(session, run) in one transaction and closes the run.

    `work` fills the counts of the run. If it raises, its transaction is rolled back, the run
    is kept as failed with the error, and the exception goes on.
    """
    with Session(engine) as session:
        run = IngestionRun(source=source, source_url=url)
        session.add(run)
        session.commit()
        run_id = run.id

    try:
        with Session(engine) as session:
            run = session.get(IngestionRun, run_id)
            work(session, run)
            run.status = "succeeded"
            run.finished_at = datetime.now(UTC)
            session.commit()
            log.info(
                "run finished",
                extra={
                    "source": source,
                    "rows_read": run.rows_read,
                    "rows_loaded": run.rows_loaded,
                    "rows_rejected": run.rows_rejected,
                },
            )
    except Exception as error:
        # Nothing of the work is left; only the failure is kept.
        with Session(engine) as session:
            failed = session.get(IngestionRun, run_id)
            failed.status = "failed"
            failed.finished_at = datetime.now(UTC)
            failed.error = str(error)
            session.commit()
        log.exception("run failed", extra={"source": source, "error": str(error)})
        raise
