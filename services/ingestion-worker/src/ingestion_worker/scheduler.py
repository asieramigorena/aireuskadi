"""Runs the loads when they are due, for as long as the worker is up.

The memory of the scheduler is core.ingestion_run: it asks when each source last succeeded, so a
restart of the container does not lose anything and no other state is needed.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    source: str  # as in ingestion_run.source
    every: timedelta  # how often it has to succeed
    run: Callable[[], None]  # does the load and raises if it fails
    retry_after: timedelta = timedelta(minutes=10)  # wait after a failure, not a whole interval
    requires: tuple[str, ...] = ()  # sources that must have succeeded once before this one


@dataclass(frozen=True)
class RunHistory:
    last_success: datetime | None
    last_attempt: datetime | None


def is_due(job: Job, history: dict[str, RunHistory], now: datetime) -> bool:
    for needed in job.requires:
        if needed not in history or history[needed].last_success is None:
            return False
    past = history.get(job.source)
    if past is None:
        return True
    if past.last_success is not None and now - past.last_success < job.every:
        return False
    # It is due. If the last attempt did not succeed (it failed, or it is still running) it waits a
    # little: no hammering a source that is down. After a success there is nothing to wait for.
    failed_since = past.last_attempt is not None and (
        past.last_success is None or past.last_attempt > past.last_success
    )
    return not failed_since or now - past.last_attempt >= job.retry_after


def run_due_jobs(jobs: list[Job], history: dict[str, RunHistory], now: datetime) -> None:
    """Runs, in order, the jobs that are due. One that fails is logged and does not stop the rest:
    the failed run itself is already recorded in ingestion_run by the load."""
    for job in jobs:
        if not is_due(job, history, now):
            continue
        try:
            job.run()
        except Exception as error:  # noqa: BLE001 - whatever a load raises, the scheduler goes on
            log.error("job failed", extra={"source": job.source, "error": str(error)})


def run_loop(
    jobs: list[Job],
    read: Callable[[], dict[str, RunHistory]],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    tick: timedelta = timedelta(seconds=30),
    once: bool = False,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """Looks at what is due, runs it and sleeps `tick`. With `once` it does a single pass, which
    is what a cron needs. The clock and the sleep are parameters so that a test can simulate hours
    in no time."""
    while True:
        run_due_jobs(jobs, read(), now())
        if once or should_stop():
            return
        sleep(tick.total_seconds())


def read_history(engine: Engine) -> dict[str, RunHistory]:
    """When each source last succeeded and when it was last tried, from core.ingestion_run. A run
    that is still running counts as an attempt: nothing is started twice."""
    query = text(
        """
        SELECT source,
               max(finished_at) FILTER (WHERE status = 'succeeded') AS last_success,
               max(started_at) AS last_attempt
        FROM core.ingestion_run
        GROUP BY source
        """
    )
    with engine.connect() as conn:
        return {
            row.source: RunHistory(row.last_success, row.last_attempt)
            for row in conn.execute(query)
        }


def close_stale_runs(engine: Engine, older_than: timedelta) -> int:
    """Marks as failed the runs that have been `running` for longer than `older_than`: the
    container was stopped or restarted in the middle of them. Returns how many it closed."""
    statement = text(
        """
        UPDATE core.ingestion_run
        SET status = 'failed', finished_at = now(),
            error = 'interrupted: the worker stopped before it ended'
        WHERE status = 'running' AND started_at < now() - make_interval(secs => :seconds)
        """
    )
    with engine.begin() as conn:
        return conn.execute(statement, {"seconds": older_than.total_seconds()}).rowcount


def run_scheduler(
    engine: Engine,
    jobs: list[Job],
    once: bool = False,
    tick: timedelta = timedelta(seconds=30),
    stale_after: timedelta = timedelta(hours=1),
) -> None:
    """The scheduler of the worker. It first closes the runs that a restart left in `running`, so
    they do not count as an attempt in progress, and then runs the jobs that are due: forever, or
    in a single pass with `once`."""
    closed = close_stale_runs(engine, stale_after)
    log.info(
        "scheduler started",
        extra={"jobs": [job.source for job in jobs], "once": once, "stale_runs_closed": closed},
    )
    run_loop(
        jobs,
        read=lambda: read_history(engine),
        now=lambda: datetime.now(UTC),
        sleep=time.sleep,
        tick=tick,
        once=once,
    )
