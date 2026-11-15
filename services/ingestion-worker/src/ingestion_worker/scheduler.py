"""Runs the loads when they are due, for as long as the worker is up. APScheduler is the clock: it
makes a pass every 30 seconds; this module decides, in each pass, which loads are due.

The memory of the scheduler is core.ingestion_run: it asks when each source last succeeded, so a
restart of the container does not lose anything and no other state is needed.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
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


def build_scheduler(
    jobs: list[Job],
    read: Callable[[], dict[str, RunHistory]],
    now: Callable[[], datetime],
    tick: timedelta = timedelta(seconds=30),
) -> BlockingScheduler:
    """APScheduler, with one job: a pass of the loads that are due (run_due_jobs) every `tick`,
    the first one at once. What is due is decided by the history (`read`), not by APScheduler,
    which keeps nothing: so a restart of the container loses nothing. `read` and `now` are
    parameters so that a test can give them."""
    scheduler = BlockingScheduler(timezone=UTC)
    scheduler.add_job(
        lambda: run_due_jobs(jobs, read(), now()),
        "interval",
        seconds=tick.total_seconds(),
        next_run_time=datetime.now(UTC),
        id="due-loads",
        name="the loads that are due",
        # A pass that takes longer than the tick (a big download) is not started twice, and the
        # passes that were missed meanwhile are one.
        max_instances=1,
        coalesce=True,
    )
    return scheduler


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
    # APScheduler writes two lines at every pass (every 30 s), and a warning at every tick while a
    # long load runs ("maximum number of running instances reached"): only its errors.
    logging.getLogger("apscheduler").setLevel(logging.ERROR)
    closed = close_stale_runs(engine, stale_after)
    log.info(
        "scheduler started",
        extra={"jobs": [job.source for job in jobs], "once": once, "stale_runs_closed": closed},
    )

    def read() -> dict[str, RunHistory]:
        return read_history(engine)

    if once:
        run_due_jobs(jobs, read(), datetime.now(UTC))
        return
    build_scheduler(jobs, read, lambda: datetime.now(UTC), tick).start()
