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
# start without it, the characters it may have, and where it goes. The keys of the tunnels are
# optional: a machine that does not use a tunnel has no such secret (and Tailscale only reads its key
# the first time, so that secret can be deleted later).
# url: letters, digits, "-" and "_", because a password goes inside a URL (the database, for the
# services). base64: those and "+", "/" and "=", for the token of Cloudflare, which is base64 and
# never goes in a URL. Neither allows a space, a quote, a "$" or a line break, which would add lines
# or commands to the file.
# env: a line of the file of the variables. file: a file of its own in the folder tunnel/ next to it,
# named like the variable, which the compose mounts read-only in the container that needs it: its
# value is then not in the environment of any container, so `docker inspect` does not show it.
# Security fix by Claude (audit 2026-11-26): the token of Cloudflare as a file.
SECRETS=(
  "POSTGRES_PASSWORD aireuskadi-postgres-password required url env"
  "POSTGRES_READER_PASSWORD aireuskadi-reader-password required url env"
  "POSTGRES_AUTH_PASSWORD aireuskadi-auth-password required url env"
  "JWT_SECRET aireuskadi-jwt-secret required url env"
  "TS_AUTHKEY aireuskadi-tailscale-authkey optional url env"
  "CLOUDFLARE_TUNNEL_TOKEN aireuskadi-cloudflare-token optional base64 file"
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
# The folder of the secrets that are files: the user of the container (not root) must reach them.
tokens="$folder/tunnel"
mkdir -p "$tokens"
# This folder is ours whatever SECRETS_ENV is: its permissions are set every time.
chmod 755 "$tokens"
tmp=$(mktemp "$folder/.secrets.XXXXXX")
errors=$(mktemp "$folder/.errors.XXXXXX")
# Whatever happens, no half-written file is left, and the one that was there is not touched.
trap 'rm -f "$tmp" "$errors" "$tokens"/.new-*' EXIT
# The secrets that are files: written as .new-<variable> and put in place only at the end.
files=()
gone=()

for entry in "${SECRETS[@]}"; do
  read -r variable name need chars where <<<"$entry"
  if ! encoded=$("$DOCKER" run --rm "$IMAGE" secrets secret-bundle get-secret-bundle-by-name \
      --secret-name "$name" --vault-id "$VAULT_ID" --auth instance_principal \
      --query 'data."secret-bundle-content".content' --raw-output 2>"$errors"); then
    if [ "$need" = "optional" ]; then
      # Only "it does not exist" removes the file of a secret: after any other failure (the network,
      # the CLI) the one that was there is kept. Security fix by Claude (audit 2026-11-26).
      if grep -q "NotAuthorizedOrNotFound" "$errors"; then
        echo "The optional secret $name is not in the Vault: $variable is left out." >&2
        [ "$where" = "file" ] && gone+=("$variable")
      else
        echo "The optional secret $name could not be read: $variable is left as it was." >&2
      fi
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
  if [ "$where" = "file" ]; then
    printf '%s' "$value" > "$tokens/.new-$variable"
    # Readable by the user of the container, which is not root; changed by nobody.
    chmod 444 "$tokens/.new-$variable"
    files+=("$variable")
  else
    printf '%s=%s\n' "$variable" "$value" >> "$tmp"
  fi
done

mv -f "$tmp" "$OUT"
# The file is replaced, not the folder: a container that mounts the folder sees the new one.
for variable in "${files[@]}"; do
  mv -f "$tokens/.new-$variable" "$tokens/$variable"
done
for variable in "${gone[@]}"; do
  rm -f "$tokens/$variable"
done
echo "Secrets written in $OUT"
