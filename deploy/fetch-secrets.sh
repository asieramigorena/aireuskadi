#!/usr/bin/env bash
# Reads the passwords and the keys of AirEuskadi from the OCI Vault and writes them in a file in memory.
#
# It runs on the Oracle VM, as root (systemd does it: see aireuskadi.service). The VM is its own
# identity in front of Oracle (instance principal: a dynamic group with this machine only, and a
# policy that lets it read the secrets of ONE vault), so no key is kept on the machine. The official
# CLI of Oracle is run as a container, so nothing is installed on the host.
#
# The file goes to /run, which is memory: it is gone when the machine stops, and the next start
# asks the Vault again. Nothing is printed: the passwords are in the file and nowhere else.
# Needs VAULT_ID (the OCID of the vault; it is not a secret, but it belongs to the machine and not
# to the repository: /etc/aireuskadi/vault.env).
set -euo pipefail
# The same letters whatever the language of the machine: the check of the value below depends on it.
LC_ALL=C

DOCKER="${DOCKER:-docker}"
OUT="${SECRETS_ENV:-/run/aireuskadi/secrets.env}"
# The CLI that Oracle publishes, by its date and by its digest: it does not change by itself.
IMAGE="ghcr.io/oracle/oci-cli:20261111@sha256:2127c2f50ee1353fa78cbf538ab91ffaccc0d02b6d0b4144530cef6ee69709f5"

# The variable of docker-compose.prod.yml, the name of its secret in the vault, whether the stack can
# start without it, and the characters it may have. The keys of the tunnels are optional: a machine
# that does not use a tunnel has no such secret (and Tailscale only reads its key the first time, so
# that secret can be deleted later).
# url: letters, digits, "-" and "_", because a password goes inside a URL (the database, for the
# services). base64: those and "+", "/" and "=", for the token of Cloudflare, which is base64 and
# never goes in a URL. Neither allows a space, a quote, a "$" or a line break, which would add lines
# or commands to the file.
SECRETS=(
  "POSTGRES_PASSWORD aireuskadi-postgres-password required url"
  "POSTGRES_READER_PASSWORD aireuskadi-reader-password required url"
  "POSTGRES_AUTH_PASSWORD aireuskadi-auth-password required url"
  "JWT_SECRET aireuskadi-jwt-secret required url"
  "TS_AUTHKEY aireuskadi-tailscale-authkey optional url"
  "CLOUDFLARE_TUNNEL_TOKEN aireuskadi-cloudflare-token optional base64"
)

: "${VAULT_ID:?VAULT_ID is not set: put it in /etc/aireuskadi/vault.env}"

umask 077
folder=$(dirname "$OUT")
# Only a folder that is made here is closed: SECRETS_ENV can be pointed anywhere, and the script runs
# as root, so the permissions of a folder that was already there (/tmp, /run) are not touched. What
# keeps the secret is the file, which is 0600 and replaced whole.
if [ ! -d "$folder" ]; then
  mkdir -m 700 -p "$folder"
fi
tmp=$(mktemp "$folder/.secrets.XXXXXX")
errors=$(mktemp "$folder/.errors.XXXXXX")
# Whatever happens, no half-written file is left, and the one that was there is not touched.
trap 'rm -f "$tmp" "$errors"' EXIT

for entry in "${SECRETS[@]}"; do
  read -r variable name need chars <<<"$entry"
  if ! encoded=$("$DOCKER" run --rm "$IMAGE" secrets secret-bundle get-secret-bundle-by-name \
      --secret-name "$name" --vault-id "$VAULT_ID" --auth instance_principal \
      --query 'data."secret-bundle-content".content' --raw-output 2>"$errors"); then
    if [ "$need" = "optional" ]; then
      echo "The optional secret $name is not in the Vault: $variable is left out." >&2
      continue
    fi
    echo "Could not read the secret $name from the Vault:" >&2
    cat "$errors" >&2
    exit 1
  fi
  if ! value=$(printf %s "$encoded" | base64 -d 2>/dev/null); then
    echo "The secret $name is not base64, which is how the Vault gives it." >&2
    exit 1
  fi
  if [ "$chars" = "base64" ]; then
    allowed='^[A-Za-z0-9_+/=-]+$'
  else
    allowed='^[A-Za-z0-9_-]+$'
  fi
  if [[ ! "$value" =~ $allowed ]]; then
    echo "The secret $name is empty or has characters that are not allowed for it ($chars, see SECRETS)." >&2
    exit 1
  fi
  printf '%s=%s\n' "$variable" "$value" >> "$tmp"
done

mv -f "$tmp" "$OUT"
echo "Secrets written in $OUT"
