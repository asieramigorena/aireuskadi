"""deploy/update.sh: what the timer of the VM runs every five minutes to keep it at `pro`.

The real thing needs git, Docker and the stack, so `git`, `runuser` and `docker` are fakes that
write down how they were called and answer what the test says: the commit of `pro`, the files that
changed, the services of the compose and the ones that are running.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "update.sh"

FAKE_GIT = r"""#!/usr/bin/env bash
echo "git $*" >> "$FAKE_CALLS"
case "$1" in
  fetch) if [ -f "$FAKE_DIR/git-fails" ]; then echo "fatal: unable to access" >&2; exit 1; fi ;;
  rev-parse) cat "$FAKE_DIR/head" ;;
  diff) cat "$FAKE_DIR/changed" 2>/dev/null || true ;;
esac
"""
FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_CALLS"
case "$*" in
  *"config --services"*)
    if [ -f "$FAKE_DIR/compose-broken" ]; then echo "invalid compose file" >&2; exit 1; fi
    cat "$FAKE_DIR/services" ;;
  *"ps --services --status running"*) printf 'api-gateway\ngrafana\n' ;;
  *" up -d --remove-orphans"*) if [ -f "$FAKE_DIR/up-fails" ]; then exit 1; fi ;;
esac
"""
# runuser -u <user> -- <command...>: writes itself down and then runs the command, like the real one.
FAKE_RUNUSER = r"""#!/usr/bin/env bash
echo "runuser $*" >> "$FAKE_CALLS"
while [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""


@pytest.fixture
def vm(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, text in (("git", FAKE_GIT), ("docker", FAKE_DOCKER), ("runuser", FAKE_RUNUSER)):
        (bin_dir / name).write_text(text)
        (bin_dir / name).chmod(0o755)
    (tmp_path / "repo").mkdir()
    (tmp_path / "secrets.env").write_text("POSTGRES_PASSWORD=x\n")
    (tmp_path / "head").write_text("bbb\n")
    (tmp_path / "services").write_text("postgres\ndb-init\napi-gateway\ngrafana\n")
    return tmp_path


def update(vm):
    env = {
        "PATH": f"{vm / 'bin'}:{os.environ['PATH']}",
        "FAKE_CALLS": str(vm / "calls.txt"),
        "FAKE_DIR": str(vm),
        "AIREUSKADI_REPO": str(vm / "repo"),
        "AIREUSKADI_SECRETS": str(vm / "secrets.env"),
        "AIREUSKADI_DEPLOYED": str(vm / "deployed"),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], check=False, env=env, capture_output=True, text=True
    )
    calls = (vm / "calls.txt").read_text().splitlines() if (vm / "calls.txt").exists() else []
    return result, [call for call in calls if call.startswith("docker")], calls


def compose(vm):
    return (
        f"docker compose --env-file .env --env-file {vm / 'secrets.env'} -f docker-compose.prod.yml"
    )


def test_a_new_commit_of_pro_is_deployed_and_remembered(vm):
    (vm / "deployed").write_text("aaa\n")

    result, docker, calls = update(vm)

    assert result.returncode == 0, result.stderr
    # The VM is a copy of pro: what someone changed by hand in the folder does not stop it.
    assert "git fetch --quiet origin pro" in calls
    assert "git reset --hard --quiet origin/pro" in calls
    assert all(
        call.startswith("runuser -u ubuntu --") for call in calls if call.startswith("runuser")
    )
    assert docker == [
        f"{compose(vm)} config --services",
        # Every image but the one of the database: a new PostgreSQL can change the format of the
        # data, so that one is changed by hand.
        f"{compose(vm)} pull --quiet db-init api-gateway grafana",
        f"{compose(vm)} up -d --remove-orphans",
        "docker image prune --force",
    ]
    assert (vm / "deployed").read_text().strip() == "bbb"


def test_with_nothing_new_on_pro_nothing_is_pulled_or_started(vm):
    # The images of a promotion come with its commit: without a new commit there is nothing to do
    # (and db-init does not run every five minutes).
    (vm / "deployed").write_text("bbb\n")

    result, docker, _ = update(vm)

    assert result.returncode == 0
    assert docker == []


def test_the_services_that_mount_a_file_that_changed_are_created_again(vm):
    # A container sees a new version of a file that it mounts only when it is created again.
    (vm / "deployed").write_text("aaa\n")
    (vm / "changed").write_text("observability/grafana-alerts.yml\n")

    _, docker, calls = update(vm)

    assert "git diff --name-only aaa bbb -- observability tunnel" in calls
    # Only the ones that are running (grafana here): naming a stopped one would start it.
    assert docker[-2] == f"{compose(vm)} up -d --force-recreate --no-deps grafana"


def test_the_first_time_everything_is_deployed_and_the_mounted_files_are_read_again(vm):
    result, docker, _ = update(vm)

    assert result.returncode == 0, result.stderr
    assert f"{compose(vm)} up -d --remove-orphans" in docker
    assert f"{compose(vm)} up -d --force-recreate --no-deps grafana" in docker
    assert (vm / "deployed").read_text().strip() == "bbb"


def test_a_deployment_that_fails_is_not_remembered_so_the_next_time_tries_again(vm):
    (vm / "deployed").write_text("aaa\n")
    (vm / "up-fails").write_text("")

    result, _, _ = update(vm)

    assert result.returncode != 0
    assert (vm / "deployed").read_text().strip() == "aaa"


def test_without_the_secrets_of_the_vault_it_does_nothing_and_waits_for_the_next_time(vm):
    # Right after a start of the VM, before aireuskadi.service has read the Vault.
    (vm / "secrets.env").unlink()

    result, _, calls = update(vm)

    assert result.returncode == 0
    assert calls == []


def test_if_git_fails_nothing_is_started_and_the_timer_sees_the_failure(vm):
    (vm / "git-fails").write_text("")

    result, docker, _ = update(vm)

    assert result.returncode != 0
    assert docker == []


@pytest.mark.parametrize("broken", ["compose-broken", "only-postgres"])
def test_if_the_compose_cannot_be_read_no_image_is_pulled(vm, broken):
    # An empty list of services would make `pull` pull every image, the database too.
    if broken == "compose-broken":
        (vm / "compose-broken").write_text("")
    else:
        (vm / "services").write_text("postgres\n")

    result, docker, _ = update(vm)

    assert result.returncode != 0
    assert not any(" pull " in call or " up " in call for call in docker)
    assert not (vm / "deployed").exists()
