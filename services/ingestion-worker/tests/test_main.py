import pytest
from ingestion_worker.main import main


def test_without_database_url_the_command_says_what_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="DATABASE_URL"):
        main(["boundaries"])
