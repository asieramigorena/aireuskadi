"""deploy/aireuskadi-update.service and .timer: systemd runs update.sh every five minutes."""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
SERVICE = (DEPLOY / "aireuskadi-update.service").read_text()
TIMER = (DEPLOY / "aireuskadi-update.timer").read_text()


def option(text: str, name: str) -> list[str]:
    return re.findall(rf"^{name}=(.*)$", text, flags=re.MULTILINE)


def test_the_timer_runs_the_update_some_minutes_after_the_start_and_then_every_five_minutes():
    assert option(TIMER, "OnBootSec") == ["5min"]
    assert option(TIMER, "OnUnitActiveSec") == ["5min"]
    assert option(TIMER, "Unit") == ["aireuskadi-update.service"]
    assert option(TIMER, "WantedBy") == ["timers.target"]


def test_the_update_runs_once_each_time_after_the_stack_and_with_docker_and_the_network():
    assert option(SERVICE, "Type") == ["oneshot"]
    assert "aireuskadi.service" in option(SERVICE, "After")[0]
    assert "docker.service" in option(SERVICE, "Requires")[0]
    assert "network-online.target" in option(SERVICE, "After")[0]


def test_what_root_runs_is_installed_in_a_folder_of_root_and_not_run_from_the_repository():
    assert option(SERVICE, "ExecStart") == ["/usr/local/sbin/aireuskadi-update"]
    assert (
        "install -m 755 -o root -g root deploy/update.sh /usr/local/sbin/aireuskadi-update"
        in SERVICE
    )


def test_it_keeps_what_it_deployed_in_a_folder_of_its_own_and_cannot_gain_privileges():
    assert option(SERVICE, "StateDirectory") == ["aireuskadi"]
    assert option(SERVICE, "NoNewPrivileges") == ["yes"]
