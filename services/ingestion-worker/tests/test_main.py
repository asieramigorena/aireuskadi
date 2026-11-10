import pytest
from ingestion_worker.main import main


def test_without_database_url_the_command_says_what_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="DATABASE_URL"):
        main(["boundaries"])


def test_the_schedule_command_starts_the_scheduler_with_the_three_jobs_and_once_asks_for_one_pass(
    monkeypatch,
):
    calls = []

    def fake_scheduler(engine, jobs, once=False):  # the real one loops forever
        calls.append(([job.source for job in jobs], once))

    monkeypatch.setattr("ingestion_worker.main.run_scheduler", fake_scheduler)

    main(["schedule"], engine=object())
    main(["schedule", "--once"], engine=object())

    sources = ["boundaries", "eprtr_air", "measurements"]
    assert calls == [(sources, False), (sources, True)]
