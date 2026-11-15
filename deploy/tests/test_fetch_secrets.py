"""deploy/fetch-secrets.sh: reads the passwords of the OCI Vault and writes them in a file in memory.

The real thing needs the Vault and the identity of the VM, so `docker` is a fake that answers like
the CLI of Oracle does (the content of the secret, in base64) and remembers how it was called.
"""

import base64
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "fetch-secrets.sh"
VAULT = "ocid1.vault.oc1.eu-madrid-1.exampleexample.abcdef"
# Long enough that they cannot appear by chance in an output.
OWNER = "Owner-Password_0123456789abcdefghij"
READER = "Reader-Password_0123456789abcdefghij"
# The shape of a one-time key of Tailscale: letters, digits and "-".
TAILSCALE = "tskey-auth-kAbC123CNTRL-0123456789abcdefghijklmnopqrstuvwxyz"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# Answers like `docker run ... oci secrets secret-bundle get-secret-bundle-by-name ...`.
echo "$@" >> "$FAKE_CALLS"
name=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--secret-name" ]; then name="$2"; fi
  shift
done
if [ -f "$FAKE_FAIL" ] && grep -qx "$name" "$FAKE_FAIL"; then
  echo "ServiceError: the secret $name cannot be read" >&2
  exit 1
fi
if [ ! -f "$FAKE_SECRETS/$name" ]; then
  echo "ServiceError: NotAuthorizedOrNotFound, the secret $name does not exist" >&2
  exit 1
fi
printf %s "$(cat "$FAKE_SECRETS/$name")" | base64 -w0
echo
echo
"""


@pytest.fixture
def machine(tmp_path):
    """A fake Docker, the secrets that it knows, and where the file is to be written."""
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "aireuskadi-postgres-password").write_text(OWNER)
    (secrets / "aireuskadi-reader-password").write_text(READER)
    docker = tmp_path / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    calls = tmp_path / "calls.txt"
    env = {
        "PATH": os.environ["PATH"],
        "DOCKER": str(docker),
        "VAULT_ID": VAULT,
        "SECRETS_ENV": str(tmp_path / "run" / "aireuskadi" / "secrets.env"),
        "FAKE_SECRETS": str(secrets),
        "FAKE_CALLS": str(calls),
        "FAKE_FAIL": str(tmp_path / "fail.txt"),
    }
    return {
        "env": env,
        "secrets": secrets,
        "calls": calls,
        "out": Path(env["SECRETS_ENV"]),
        "fail": Path(env["FAKE_FAIL"]),
    }


def run(machine, **changes):
    env = {**machine["env"], **changes}
    env = {key: value for key, value in env.items() if value is not None}
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30, check=False
    )


def written(machine) -> dict[str, str]:
    lines = machine["out"].read_text().splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_the_two_passwords_are_written_with_the_names_of_the_variables_of_the_compose(machine):
    result = run(machine)

    assert result.returncode == 0, result.stderr
    assert written(machine) == {"POSTGRES_PASSWORD": OWNER, "POSTGRES_READER_PASSWORD": READER}


def test_the_file_and_its_folder_are_only_for_the_owner(machine):
    run(machine)

    assert stat.S_IMODE(machine["out"].stat().st_mode) == 0o600
    assert stat.S_IMODE(machine["out"].parent.stat().st_mode) == 0o700


def test_a_folder_that_was_there_is_not_changed_the_file_inside_is_what_keeps_the_secret(machine):
    # SECRETS_ENV can be pointed anywhere, and the script runs as root: it must never take the
    # permissions of a folder that it did not make (/tmp, /etc) away.
    machine["out"].parent.mkdir(parents=True)
    machine["out"].parent.chmod(0o755)

    run(machine)

    assert stat.S_IMODE(machine["out"].parent.stat().st_mode) == 0o755
    assert stat.S_IMODE(machine["out"].stat().st_mode) == 0o600


def test_no_temporary_file_is_left_behind_after_a_success_or_a_failure(machine):
    run(machine)
    machine["fail"].write_text("aireuskadi-reader-password\n")
    run(machine)

    assert sorted(path.name for path in machine["out"].parent.iterdir()) == ["secrets.env"]


def test_the_script_is_executable_because_systemd_runs_it_directly_and_not_with_bash():
    assert os.access(SCRIPT, os.X_OK)


def test_nothing_of_the_passwords_is_printed(machine):
    result = run(machine)

    for text in (result.stdout, result.stderr):
        assert OWNER not in text
        assert READER not in text


def test_the_vault_is_asked_with_the_identity_of_the_machine_and_by_the_name_of_each_secret(
    machine,
):
    run(machine)

    calls = machine["calls"].read_text().splitlines()
    names = [
        "aireuskadi-postgres-password",
        "aireuskadi-reader-password",
        "aireuskadi-tailscale-authkey",
    ]
    assert len(calls) == len(names)
    for call, name in zip(calls, names, strict=True):
        assert call.startswith("run --rm ")
        assert "--auth instance_principal" in call
        assert f"--vault-id {VAULT}" in call
        assert f"--secret-name {name}" in call


def test_the_image_of_the_cli_is_the_official_one_and_pinned_by_its_digest(machine):
    run(machine)

    call = machine["calls"].read_text().splitlines()[0]
    assert re.search(r"ghcr\.io/oracle/oci-cli:\S+@sha256:[0-9a-f]{64}\b", call)


def test_a_password_that_cannot_be_read_stops_everything_and_leaves_no_file(machine):
    machine["fail"].write_text("aireuskadi-reader-password\n")

    result = run(machine)

    assert result.returncode != 0
    assert not machine["out"].exists()
    assert "aireuskadi-reader-password" in result.stderr
    assert OWNER not in result.stderr + result.stdout


def test_the_file_that_was_there_is_not_touched_when_a_read_fails(machine):
    machine["out"].parent.mkdir(parents=True)
    machine["out"].write_text("POSTGRES_PASSWORD=the-one-that-was-working\n")
    machine["fail"].write_text("aireuskadi-postgres-password\n")

    result = run(machine)

    assert result.returncode != 0
    assert machine["out"].read_text() == "POSTGRES_PASSWORD=the-one-that-was-working\n"


@pytest.mark.parametrize(
    "bad",
    ["has/slash", "has+plus", "has@at", "has:colon", "has space", "has'quote", "", "line\nbreak"],
)
def test_a_password_that_would_break_the_url_of_the_database_is_refused(machine, bad):
    (machine["secrets"] / "aireuskadi-postgres-password").write_text(bad)

    result = run(machine)

    assert result.returncode != 0
    assert not machine["out"].exists()
    assert "aireuskadi-postgres-password" in result.stderr
    if bad.strip():
        assert bad not in result.stderr


def test_without_the_id_of_the_vault_it_says_so_and_asks_nothing(machine):
    result = run(machine, VAULT_ID=None)

    assert result.returncode != 0
    assert "VAULT_ID" in result.stderr
    assert not machine["calls"].exists()


def test_running_it_again_replaces_the_file_with_what_the_vault_says_now(machine):
    run(machine)
    (machine["secrets"] / "aireuskadi-postgres-password").write_text(
        "New-Owner-Password_9876543210"
    )

    result = run(machine)

    assert result.returncode == 0, result.stderr
    assert written(machine)["POSTGRES_PASSWORD"] == "New-Owner-Password_9876543210"
    assert written(machine)["POSTGRES_READER_PASSWORD"] == READER


def test_the_file_is_the_same_whatever_the_umask_of_whoever_runs_it(machine):
    env = {**machine["env"]}
    result = subprocess.run(
        ["bash", "-c", f'umask 000; bash "{SCRIPT}"'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(machine["out"].stat().st_mode) == 0o600


def test_the_secret_in_base64_is_decoded_as_the_vault_gives_it(machine):
    # The vault answers in base64 with no line break; a password with "=" or "-" or "_" is kept whole.
    value = "A-b_C-d_E1234567890-xyz_Q"
    (machine["secrets"] / "aireuskadi-reader-password").write_text(value)

    run(machine)

    assert written(machine)["POSTGRES_READER_PASSWORD"] == value
    assert base64.b64encode(value.encode()).decode() not in machine["out"].read_text()


def test_the_key_of_the_tunnel_is_written_too_when_there_is_one(machine):
    (machine["secrets"] / "aireuskadi-tailscale-authkey").write_text(TAILSCALE)

    result = run(machine)

    assert result.returncode == 0, result.stderr
    assert written(machine) == {
        "POSTGRES_PASSWORD": OWNER,
        "POSTGRES_READER_PASSWORD": READER,
        "TS_AUTHKEY": TAILSCALE,
    }
    assert TAILSCALE not in result.stdout + result.stderr


def test_without_the_key_of_the_tunnel_the_rest_is_written_and_it_is_said_that_there_was_none(
    machine,
):
    # The tunnel is optional: a machine that does not use it has no such secret in its vault.
    result = run(machine)

    assert result.returncode == 0, result.stderr
    assert written(machine) == {"POSTGRES_PASSWORD": OWNER, "POSTGRES_READER_PASSWORD": READER}
    assert "aireuskadi-tailscale-authkey" in result.stderr


def test_a_password_that_is_missing_is_not_skipped_like_the_key_of_the_tunnel(machine):
    (machine["secrets"] / "aireuskadi-reader-password").unlink()

    result = run(machine)

    assert result.returncode != 0
    assert not machine["out"].exists()


@pytest.mark.parametrize(
    "bad", ["key\nPOSTGRES_PASSWORD=other", "key with space", "key;rm", "ke$y"]
)
def test_a_key_of_the_tunnel_that_could_add_lines_or_commands_to_the_file_is_refused(machine, bad):
    (machine["secrets"] / "aireuskadi-tailscale-authkey").write_text(bad)

    result = run(machine)

    assert result.returncode != 0
    assert not machine["out"].exists()
    assert "other" not in result.stderr
