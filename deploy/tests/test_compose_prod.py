"""docker-compose.prod.yml: what keeps the stack of the VM closed. Nothing can be reached from
outside but through a tunnel, and Grafana believes the user that the gateway names only because
nothing else can reach it."""

from pathlib import Path

import pytest
import yaml

COMPOSE = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "docker-compose.prod.yml").read_text()
)
SERVICES = COMPOSE["services"]


def test_no_service_publishes_a_port():
    assert [name for name, service in SERVICES.items() if "ports" in service] == []


@pytest.mark.parametrize("name", ["tunnel", "cloudflared"])
def test_the_tunnels_reach_only_the_gateway_with_no_permissions_and_a_fixed_image(name):
    tunnel = SERVICES[name]

    assert tunnel["networks"] == ["edge"]
    assert tunnel["read_only"] is True
    assert tunnel["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in tunnel["security_opt"]
    assert "@sha256:" in tunnel["image"]


@pytest.mark.parametrize("name", ["api-gateway", "auth-service", "insight-service"])
def test_the_services_that_anyone_can_reach_have_a_limit_of_memory(name):
    # A flood of requests restarts the service, not the VM.
    assert SERVICES[name]["mem_limit"] == "1g"
    assert SERVICES[name]["memswap_limit"] == "1g"


def test_the_tunnels_share_their_network_only_with_the_gateway_and_grafana_is_on_its_own_one():
    def on(network):
        return sorted(
            name for name, service in SERVICES.items() if network in service.get("networks", [])
        )

    assert on("edge") == ["api-gateway", "cloudflared", "tunnel"]
    assert "api-gateway" in on("monitoring")
    assert SERVICES["grafana"]["networks"] == ["monitoring"]
    assert SERVICES["grafana"]["environment"]["GF_AUTH_DISABLE_LOGIN_FORM"] == "true"
