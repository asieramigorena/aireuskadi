"""The memory of the scheduler: core.ingestion_run. Skipped without DATABASE_URL (conftest.py)."""

from datetime import UTC, datetime, timedelta

from aireuskadi_db import IngestionRun
from ingestion_worker.scheduler import Job, close_stale_runs, read_history, run_scheduler
from sqlalchemy.orm import Session

NOW = datetime.now(UTC)


def run(source, status, started_ago, finished_ago=None):
    return IngestionRun(
        source=source,
        status=status,
        started_at=NOW - started_ago,
        finished_at=None if finished_ago is None else NOW - finished_ago,
    )


def test_the_history_has_the_last_success_and_the_last_attempt_of_each_source(engine):
    with Session(engine) as session:
        session.add_all(
            [
                # a: it succeeded 3 days ago and the attempt of 1 hour ago failed
                run("t_a", "succeeded", timedelta(days=3, minutes=1), timedelta(days=3)),
                run("t_a", "succeeded", timedelta(days=5, minutes=1), timedelta(days=5)),
                run("t_a", "failed", timedelta(hours=1), timedelta(hours=1)),
                # b: it has only failed
                run("t_b", "failed", timedelta(hours=2), timedelta(hours=2)),
                # c: it is running now
                run("t_c", "running", timedelta(minutes=2)),
            ]
        )
        session.commit()

    history = read_history(engine)

    a, b, c = history["t_a"], history["t_b"], history["t_c"]
    assert a.last_success == NOW - timedelta(days=3)
    assert a.last_attempt == NOW - timedelta(hours=1)
    assert (b.last_success, b.last_attempt) == (None, NOW - timedelta(hours=2))
    assert (c.last_success, c.last_attempt) == (None, NOW - timedelta(minutes=2))


def test_a_run_left_running_by_a_restart_is_closed_as_failed_and_a_recent_one_is_not_touched(
    engine,
):
    with Session(engine) as session:
        old = run("t_old", "running", timedelta(hours=3))
        recent = run("t_recent", "running", timedelta(minutes=5))
        done = run("t_done", "succeeded", timedelta(hours=5), timedelta(hours=5))
        session.add_all([old, recent, done])
        session.commit()
        ids = (old.id, recent.id, done.id)

    closed = close_stale_runs(engine, older_than=timedelta(hours=1))

    with Session(engine) as session:
        old, recent, done = (session.get(IngestionRun, i) for i in ids)
        assert (old.status, old.error) == (
            "failed",
            "interrupted: the worker stopped before it ended",
        )
        assert old.finished_at is not None
        assert (recent.status, recent.finished_at) == ("running", None)
        assert done.status == "succeeded"
    assert closed >= 1


def test_a_pass_closes_what_a_restart_left_hanging_and_then_runs_what_is_due(engine):
    with Session(engine) as session:
        hanging = run("t_hang", "running", timedelta(hours=3))
        session.add(hanging)
        session.commit()
        hanging_id = hanging.id
    ran = []
    jobs = [
        Job("t_never_ran", timedelta(hours=1), lambda: ran.append("t_never_ran")),
        # it succeeded 10 minutes ago: not due
        Job("t_ran_lately", timedelta(hours=1), lambda: ran.append("t_ran_lately")),
    ]
    with Session(engine) as session:
        session.add(run("t_ran_lately", "succeeded", timedelta(minutes=11), timedelta(minutes=10)))
        session.commit()

    run_scheduler(engine, jobs, once=True)

    assert ran == ["t_never_ran"]
    with Session(engine) as session:
        assert session.get(IngestionRun, hanging_id).status == "failed"
