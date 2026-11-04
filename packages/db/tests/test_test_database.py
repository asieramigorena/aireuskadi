"""The pytest plugin that points the tests to a database of their own (packages/db/tests/testing.py).

It is run in a pytest that is started on purpose (a subprocess), because what is
tested is what happens when pytest starts: whether the session survives a server that is down or
several sessions that start at the same time and all want to create the same database.
"""

import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

HERE = Path(__file__).resolve().parent
URL = os.environ.get("DATABASE_URL")

PROBE = """
import os

def test_the_session_runs():
    url = os.environ.get("DATABASE_URL")
    # Only the name of the database is printed: the URL has a password.
    print("DATABASE=" + str(url.rsplit("/", 1)[-1] if url else None))
"""


def run_pytest(tmp_path, database_url):
    """Run a pytest with the plugin; returns the finished process."""
    tmp_path.mkdir(exist_ok=True)
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE)
    env = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": str(HERE)}
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-p", "testing", "-s",
         "-p", "no:cacheprovider", "--rootdir", str(tmp_path)],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip


def test_a_server_that_is_down_does_not_stop_the_tests_that_do_not_need_it(tmp_path):
    # Nothing listens on port 1. The tests of the database are skipped (as without DATABASE_URL)
    # instead of being sent to the database of the application, and the others still run.
    result = run_pytest(tmp_path, "postgresql+psycopg://u:p@127.0.0.1:1/aireuskadi")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert "DATABASE=None" in result.stdout
    assert "cannot reach the server" in result.stdout


@pytest.mark.skipif(not URL, reason="DATABASE_URL is not set")
def test_sessions_that_start_together_all_find_the_database_of_the_tests(tmp_path):
    scratch = "t_race_" + uuid.uuid4().hex[:8]
    base = make_url(URL)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{scratch}"'))
        url = base.set(database=scratch).render_as_string(hide_password=False)

        with ThreadPoolExecutor(max_workers=6) as pool:
            sessions = list(pool.map(lambda i: run_pytest(tmp_path / str(i), url), range(6)))
    finally:
        with admin.connect() as conn:
            for name in (scratch, scratch + "_test"):
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()

    for session in sessions:
        assert session.returncode == 0, session.stdout + session.stderr
        assert f"DATABASE={scratch}_test" in session.stdout
