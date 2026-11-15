from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from ingestion_worker.scheduler import Job, RunHistory, build_scheduler, is_due, run_due_jobs

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def job(source="measurements", every=timedelta(hours=1), **options):
    return Job(source=source, every=every, run=lambda: None, **options)


def test_a_job_that_has_never_run_is_due():
    assert is_due(job(), {}, NOW)


def test_a_job_that_succeeded_less_than_its_interval_ago_is_not_due():
    done = RunHistory(
        last_success=NOW - timedelta(minutes=59), last_attempt=NOW - timedelta(minutes=59)
    )

    assert not is_due(job(every=timedelta(hours=1)), {"measurements": done}, NOW)


def test_a_job_that_succeeded_longer_ago_than_its_interval_is_due():
    done = RunHistory(
        last_success=NOW - timedelta(minutes=61), last_attempt=NOW - timedelta(minutes=61)
    )

    assert is_due(job(every=timedelta(hours=1)), {"measurements": done}, NOW)


def failed_since(minutes):
    """It succeeded two hours ago and the attempt that followed failed `minutes` ago."""
    return {
        "measurements": RunHistory(
            last_success=NOW - timedelta(hours=2), last_attempt=NOW - timedelta(minutes=minutes)
        )
    }


def test_a_job_that_has_just_failed_waits_before_trying_again():
    assert not is_due(job(retry_after=timedelta(minutes=10)), failed_since(3), NOW)


def test_a_job_that_failed_longer_ago_than_the_wait_is_tried_again_without_waiting_for_its_interval():
    assert is_due(job(retry_after=timedelta(minutes=10)), failed_since(11), NOW)


def test_a_job_waits_until_the_sources_it_needs_have_succeeded_once():
    needs_boundaries = job(requires=("boundaries",))
    only_failed = {
        "boundaries": RunHistory(last_success=None, last_attempt=NOW - timedelta(hours=1))
    }
    succeeded = {"boundaries": RunHistory(last_success=NOW - timedelta(days=3), last_attempt=NOW)}

    assert not is_due(needs_boundaries, {}, NOW)
    assert not is_due(needs_boundaries, only_failed, NOW)
    assert is_due(needs_boundaries, succeeded, NOW)


def test_a_job_that_fails_is_logged_and_the_next_ones_still_run(caplog):
    calls = []

    def boom():
        calls.append("boundaries")
        raise RuntimeError("the server is down")

    jobs = [
        Job("boundaries", timedelta(days=30), boom),
        Job("eprtr_air", timedelta(days=30), lambda: calls.append("eprtr_air")),
        Job("measurements", timedelta(hours=1), lambda: calls.append("measurements")),
    ]
    recent = RunHistory(
        last_success=NOW - timedelta(minutes=5), last_attempt=NOW - timedelta(minutes=5)
    )

    with caplog.at_level("ERROR", logger="ingestion_worker.scheduler"):
        run_due_jobs(jobs, {"measurements": recent}, NOW)  # measurements ran 5 minutes ago

    assert calls == ["boundaries", "eprtr_air"]  # in order; the failure did not stop the next one
    (record,) = caplog.records
    assert (record.getMessage(), record.source) == ("job failed", "boundaries")
    assert "the server is down" in record.error


class World:
    """A clock that only moves when it is told, and the history that the jobs write. `passes` does
    what APScheduler does in the container: a pass of the due jobs every `tick`."""

    def __init__(self):
        self.clock = NOW
        self.history = {}
        self.attempts = []  # minutes after the start at which a job was tried

    def now(self):
        return self.clock

    def passes(self, jobs, tick, until):
        while self.clock < until:
            run_due_jobs(jobs, self.read(), self.now())
            self.clock += tick

    def read(self):
        return dict(self.history)

    def job(self, source, every, fail=lambda attempt: False, **options):
        def run():
            attempt = len([a for a in self.attempts if a[0] == source])
            self.attempts.append((source, int((self.clock - NOW).total_seconds() // 60)))
            before = self.history.get(source)
            ok = not fail(attempt)
            self.history[source] = RunHistory(
                last_success=self.clock if ok else (before.last_success if before else None),
                last_attempt=self.clock,
            )
            if not ok:
                raise RuntimeError("down")

        return Job(source, every, run, **options)

    def minutes(self, source):
        return [m for s, m in self.attempts if s == source]


def test_an_hourly_job_runs_at_the_start_and_then_once_an_hour_not_in_every_pass():
    world = World()
    jobs = [world.job("measurements", timedelta(hours=1))]

    world.passes(jobs, tick=timedelta(minutes=10), until=NOW + timedelta(minutes=150))

    assert world.minutes("measurements") == [0, 60, 120]


def test_after_a_failure_the_job_is_tried_again_when_the_wait_ends_and_not_in_every_pass():
    world = World()
    jobs = [
        world.job(
            "measurements",
            timedelta(hours=1),
            fail=lambda attempt: attempt < 2,  # the first two attempts fail
            retry_after=timedelta(minutes=10),
        )
    ]

    world.passes(jobs, tick=timedelta(minutes=5), until=NOW + timedelta(minutes=30))

    # Fails, fails, succeeds; then it waits an hour.
    assert world.minutes("measurements") == [0, 10, 20]


def test_apscheduler_makes_a_pass_every_tick_starting_now():
    jobs = [job()]

    scheduler = build_scheduler(jobs, read=dict, now=lambda: NOW, tick=timedelta(seconds=30))

    assert isinstance(scheduler, BlockingScheduler)
    (scheduled,) = scheduler.get_jobs()
    assert isinstance(scheduled.trigger, IntervalTrigger)
    assert scheduled.trigger.interval == timedelta(seconds=30)
    # The first pass at once: a worker that starts does not wait half a minute to look.
    assert scheduled.next_run_time <= datetime.now(UTC)
    # A pass that takes longer than the tick (a big download) is not started twice, and the passes
    # that were missed meanwhile are one, not a burst.
    assert scheduled.max_instances == 1
    assert scheduled.coalesce is True


def test_the_pass_of_apscheduler_runs_the_jobs_that_are_due():
    ran = []
    recent = RunHistory(last_success=NOW, last_attempt=NOW)
    jobs = [
        Job("boundaries", timedelta(days=30), lambda: ran.append("boundaries")),
        Job("measurements", timedelta(hours=1), lambda: ran.append("measurements")),
    ]
    scheduler = build_scheduler(
        jobs, read=lambda: {"boundaries": recent}, now=lambda: NOW, tick=timedelta(seconds=30)
    )

    (scheduled,) = scheduler.get_jobs()
    scheduled.func()

    assert ran == ["measurements"]


def test_a_job_that_succeeded_and_is_due_again_is_not_held_back_by_the_wait_after_a_failure():
    # Every 5 minutes, with a wait of 10 after a failure. It succeeded 6 minutes ago: its last
    # attempt is that success, not a failure, so the wait does not apply.
    done = RunHistory(
        last_success=NOW - timedelta(minutes=5, seconds=30), last_attempt=NOW - timedelta(minutes=6)
    )
    short = job(every=timedelta(minutes=5), retry_after=timedelta(minutes=10))

    assert is_due(short, {"measurements": done}, NOW)
