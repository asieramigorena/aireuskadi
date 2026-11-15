"""deploy/aireuskadi.service: what systemd runs when the VM starts."""

import re
from pathlib import Path

UNIT = (Path(__file__).resolve().parents[1] / "aireuskadi.service").read_text()


def option(name: str) -> list[str]:
    return re.findall(rf"^{name}=(.*)$", UNIT, flags=re.MULTILINE)


def test_it_runs_once_per_start_and_stays_active_so_that_it_can_be_restarted_to_rotate_a_password():
    assert option("Type") == ["oneshot"]
    assert option("RemainAfterExit") == ["yes"]


def test_it_waits_for_docker_and_for_the_network_because_the_vault_is_asked_over_it():
    assert "docker.service" in option("After")[0]
    assert "network-online.target" in option("After")[0]
    assert "docker.service" in option("Requires")[0]


def test_the_id_of_the_vault_comes_from_a_file_of_the_machine_and_not_from_the_repository():
    assert option("EnvironmentFile") == ["/etc/aireuskadi/vault.env"]
    assert "ocid1." not in UNIT


def test_first_it_reads_the_secrets_and_then_it_starts_the_stack_with_them_and_with_the_other_variables():
    starts = option("ExecStart")
    assert len(starts) == 2
    assert starts[0] == "/usr/local/sbin/aireuskadi-fetch-secrets"
    assert "docker compose" in starts[1]
    assert "--env-file .env" in starts[1]
    assert "--env-file /run/aireuskadi/secrets.env" in starts[1]
    assert "-f docker-compose.prod.yml" in starts[1]
    assert starts[1].rstrip().endswith("up -d")


def test_it_is_started_when_the_machine_starts():
    assert option("WantedBy") == ["multi-user.target"]


def test_there_is_no_password_in_it():
    assert not re.search(r"PASSWORD\s*=\s*\S", UNIT)


def test_what_root_runs_is_not_in_a_folder_that_the_normal_user_can_write():
    # The unit runs as root. If the script were in the home of `ubuntu`, any process of that user
    # could change it and be root at the next start: it is installed in a folder of root.
    assert not option("ExecStart")[0].startswith("/home/")
    assert (
        "install -m 755 -o root -g root deploy/fetch-secrets.sh /usr/local/sbin/aireuskadi-fetch-secrets"
        in UNIT
    )


def test_it_cannot_gain_privileges_and_has_a_temporary_folder_of_its_own():
    assert option("NoNewPrivileges") == ["yes"]
    assert option("PrivateTmp") == ["yes"]


def test_the_header_says_that_the_password_of_the_owner_of_the_database_is_not_rotated_by_a_restart():
    # The image of PostgreSQL reads it only when it makes the volume: a restart with a new one would
    # leave the services with a password that the database does not have.
    assert "ALTER ROLE" in UNIT
