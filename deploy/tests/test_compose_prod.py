"""docker-compose.prod.yml: what keeps the stack of the VM closed. Nothing can be reached from
outside but through a tunnel, and Grafana believes the user that the gateway names only from the
fixed address of the gateway."""

import ipaddress
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
def test_the_tunnels_reach_only_the_gateway_with_no_permissions(name):
    tunnel = SERVICES[name]

    assert tunnel["networks"] == ["edge"]
    assert tunnel["read_only"] is True
    assert tunnel["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in tunnel["security_opt"]


OURS = [
    "api-gateway",
    "auth-service",
    "insight-service",
    "emissions-service",
    "air-quality-service",
    "ingestion-scheduler",
    "db-init",
]


@pytest.mark.parametrize("name", OURS)
def test_our_services_cannot_change_their_files_nor_gain_permissions(name):
    service = SERVICES[name]

    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]


# All but db-init, which runs once and stops.
LONG_RUNNING = [
    "api-gateway",
    "auth-service",
    "insight-service",
    "emissions-service",
    "air-quality-service",
    "ingestion-scheduler",
    "postgres",
    "redis",
    "logouts",
    "loki",
    "prometheus",
    "alloy",
    "grafana",
    "tunnel",
    "cloudflared",
]


@pytest.mark.parametrize("name", LONG_RUNNING)
def test_every_service_that_keeps_running_has_a_limit_of_memory_with_the_swap(name):
    # A flood of requests or a leak restarts that service, not the VM.
    assert SERVICES[name]["mem_limit"]
    assert SERVICES[name]["memswap_limit"] == SERVICES[name]["mem_limit"]


def test_the_tunnels_share_their_network_only_with_the_gateway_and_grafana_is_on_its_own_one():
    def on(network):
        return sorted(
            name for name, service in SERVICES.items() if network in service.get("networks", [])
        )

    assert on("edge") == ["api-gateway", "cloudflared", "tunnel"]
    assert "api-gateway" in on("monitoring")
    assert SERVICES["grafana"]["networks"] == ["monitoring"]
    assert SERVICES["grafana"]["environment"]["GF_AUTH_DISABLE_LOGIN_FORM"] == "true"


def subnet(network: str) -> str:
    return COMPOSE["networks"][network]["ipam"]["config"][0]["subnet"]


def test_grafana_believes_only_the_fixed_address_of_the_gateway():
    gateway = SERVICES["api-gateway"]["networks"]["monitoring"]["ipv4_address"]

    assert SERVICES["grafana"]["environment"]["GF_AUTH_PROXY_WHITELIST"] == gateway
    assert ipaddress.ip_address(gateway) in ipaddress.ip_network(subnet("monitoring"))


def test_the_gateway_believes_x_forwarded_for_only_from_the_network_of_the_tunnels():
    assert SERVICES["api-gateway"]["environment"]["TUNNEL_NETWORK"] == subnet("edge")


def test_the_token_of_cloudflare_is_a_file_and_not_in_the_environment():
    cloudflared = SERVICES["cloudflared"]

    assert "TUNNEL_TOKEN" not in cloudflared["environment"]
    assert cloudflared["environment"]["TUNNEL_TOKEN_FILE"] == "/run/tunnel/CLOUDFLARE_TUNNEL_TOKEN"
    assert "/run/aireuskadi/tunnel:/run/tunnel:ro" in cloudflared["volumes"]


def test_no_other_container_can_get_the_address_of_the_gateway_that_grafana_believes():
    gateway = ipaddress.ip_address(
        SERVICES["api-gateway"]["networks"]["monitoring"]["ipv4_address"]
    )
    dynamic = COMPOSE["networks"]["monitoring"]["ipam"]["config"][0]["ip_range"]

    # Docker gives the others their addresses from `ip_range` only.
    assert gateway not in ipaddress.ip_network(dynamic)
    # Nor can one of them answer for that address on the network (ARP), without NET_RAW.
    for name in ("loki", "prometheus", "grafana"):
        assert "NET_RAW" in SERVICES[name]["cap_drop"]


def test_the_logouts_have_a_redis_of_their_own_that_never_drops_them():
    auth, store = SERVICES["auth-service"], SERVICES["logouts"]

    # The auth service cannot touch the cache that everybody is served from.
    assert "cache" not in auth["networks"]
    assert auth["environment"]["REDIS_URL"].startswith("redis://logouts:")
    assert sorted(
        name for name, service in SERVICES.items() if "logouts" in service.get("networks", [])
    ) == [
        "auth-service",
        "logouts",
    ]
    # Full, it refuses a new logout rather than forget an old one.
    assert "noeviction" in store["command"]
