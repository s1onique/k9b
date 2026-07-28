#!/usr/bin/env bash
# install-spbnix-harbor-ca.sh
# Installs SPbNIX Harbor CA certificate into runner, Docker daemon, and BuildKit containers.
#
# Valid CA sources (at least one required):
#   A. SPBNIX_CA_CERT_PEM - nonempty valid PEM certificate content
#   B. HARBOR_CA_PATH     - existing file with expected SHA-256
#
# Exit codes:
#   0 - CA installed successfully
#   1 - HARBOR_CA_SOURCE_MISSING (neither source available)
#   2 - HARBOR_CA_INVALID (invalid PEM or empty file)
#   3 - HARBOR_CA_SHA256_MISMATCH (fingerprint mismatch)
#
set -euo pipefail

# --- Configuration ---
HARBOR_HOST="${HARBOR_HOST:-harbor-pve1.spbnix.local}"
HARBOR_CA_PATH="${HARBOR_CA_PATH:-}"
HARBOR_CA_SHA256="${HARBOR_CA_SHA256:-}"
CERT_DIR="${RUNNER_TEMP:-/tmp}/spbnix-ca"
CERT_FILE="${CERT_DIR}/spbnix-harbor-ca.crt"
mkdir -p "$CERT_DIR"

# --- Determine CA source ---
CA_SOURCE=""

# Source A: SPBNIX_CA_CERT_PEM
if [[ -n "${SPBNIX_CA_CERT_PEM:-}" ]]; then
  echo "CA source: secret (SPBNIX_CA_CERT_PEM)"
  CA_SOURCE="secret"
  
  # Validate PEM
  echo "$SPBNIX_CA_CERT_PEM" > "$CERT_FILE"
  if ! VALIDATED=$(openssl x509 -in "$CERT_FILE" -noout -subject -issuer -dates 2>&1); then
    echo "ERROR: HARBOR_CA_PEM_INVALID"
    echo "ERROR: Invalid PEM certificate in SPBNIX_CA_CERT_PEM"
    echo "openssl output: $VALIDATED"
    exit 2
  fi
  echo "CA certificate validated from secret:"
  echo "$VALIDATED"

# Source B: HARBOR_CA_PATH
elif [[ -n "$HARBOR_CA_PATH" ]]; then
  echo "CA source: runner_mount ($HARBOR_CA_PATH)"
  CA_SOURCE="runner_mount"
  
  # Check file exists
  if [[ ! -f "$HARBOR_CA_PATH" ]]; then
    echo "ERROR: HARBOR_CA_PATH_MISSING"
    echo "ERROR: CA file does not exist: $HARBOR_CA_PATH"
    exit 1
  fi
  
  # Check file is not empty
  if [[ ! -s "$HARBOR_CA_PATH" ]]; then
    echo "ERROR: HARBOR_CA_EMPTY"
    echo "ERROR: CA file is empty: $HARBOR_CA_PATH"
    exit 2
  fi
  
  # Copy to working location
  cp "$HARBOR_CA_PATH" "$CERT_FILE"
  
  # Validate PEM
  if ! VALIDATED=$(openssl x509 -in "$CERT_FILE" -noout -subject -issuer -dates 2>&1); then
    echo "ERROR: HARBOR_CA_PEM_INVALID"
    echo "ERROR: Invalid PEM in $HARBOR_CA_PATH"
    echo "openssl output: $VALIDATED"
    exit 2
  fi
  echo "CA certificate validated from runner mount:"
  echo "$VALIDATED"
  
  # Verify SHA-256 if provided
  if [[ -n "$HARBOR_CA_SHA256" ]]; then
    ACTUAL_SHA256=$(openssl x509 -in "$CERT_FILE" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//' | tr -d ':')
    if [[ "${ACTUAL_SHA256,,}" != "${HARBOR_CA_SHA256,,}" ]]; then
      echo "ERROR: HARBOR_CA_SHA256_MISMATCH"
      echo "ERROR: Expected: $HARBOR_CA_SHA256"
      echo "ERROR: Actual: $ACTUAL_SHA256"
      exit 3
    fi
    echo "CA fingerprint verified: $ACTUAL_SHA256"
  fi

# No valid source
else
  echo "ERROR: HARBOR_CA_SOURCE_MISSING"
  echo "ERROR: Neither SPBNIX_CA_CERT_PEM nor HARBOR_CA_PATH is available"
  echo ""
  echo "At least one CA source is required:"
  echo "  A. Set SPBNIX_CA_CERT_PEM secret with valid PEM certificate"
  echo "  B. Set HARBOR_CA_PATH to runner-mounted CA file"
  exit 1
fi

# Emit result
echo "CA_SOURCE=$CA_SOURCE"
echo "CA_FILE=$CERT_FILE"

# --- Helper: install with sudo if needed ---
install_file() {
  local src="$1"
  local dest="$2"
  local mode="${3:-0644}"

  if [[ -w "$(dirname "$dest")" ]]; then
    cp "$src" "$dest"
    chmod "$mode" "$dest"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo install -D -m "$mode" "$src" "$dest"
  else
    echo "ERROR: Cannot write to $(dirname "$dest")"
    exit 4
  fi
}

# --- Install into runner system trust (for curl, openssl, etc.) ---
install_into_runner_trust() {
  echo "Installing CA into runner system trust store..."

  local dest=""
  local updated=0

  if [[ -w /usr/local/share/ca-certificates ]]; then
    dest="/usr/local/share/ca-certificates/spbnix-harbor-ca.crt"
    cp "$CERT_FILE" "$dest"
    updated=1
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    dest="/usr/local/share/ca-certificates/spbnix-harbor-ca.crt"
    sudo cp "$CERT_FILE" "$dest"
    updated=1
  fi

  if [[ "$updated" -eq 1 ]]; then
    if command -v update-ca-certificates &>/dev/null; then
      sudo update-ca-certificates 2>/dev/null || update-ca-certificates
    else
      echo "WARNING: update-ca-certificates not available; appending to system CA bundle as fallback"
      if [[ -w /etc/ssl/certs/ca-certificates.crt ]]; then
        cat "$CERT_FILE" >> /etc/ssl/certs/ca-certificates.crt
      elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo tee -a /etc/ssl/certs/ca-certificates.crt < "$CERT_FILE" > /dev/null
      else
        echo "ERROR: Cannot install CA into runner trust: no write access to system CA store."
        exit 4
      fi
    fi
    echo "CA installed into runner system trust: $dest"
  else
    echo "ERROR: Cannot install CA into runner trust: no write access to system CA store."
    exit 4
  fi
}

# --- Install into Docker daemon trust (CRITICAL for "Error response from daemon") ---
# Docker daemon validates registry TLS using /etc/docker/certs.d/<host>/ca.crt
# This path must be accessible to the Docker daemon, not just the runner container.
# In DinD setups, the daemon runs in a sidecar container; the CA is mounted there.
#
# ARC GitHub-hosted runners use DinD sidecar for the Docker daemon. The runner-side
# /etc/docker/certs.d write is no longer authoritative after infra ESO changes.
# When SKIP_RUNNER_DOCKER_CERTS_D=1, skip runner-side install entirely and let
# the DinD sidecar own the daemon CA trust path.
install_into_docker_daemon_trust() {
  echo "Installing CA into Docker daemon trust store for $HARBOR_HOST..."

  local docker_certs_dir="/etc/docker/certs.d/${HARBOR_HOST}"
  local ca_dest="${docker_certs_dir}/ca.crt"

  # If ARC/DinD mounts the CA into the daemon sidecar, runner-side certs.d is
  # diagnostic/convenience only. Do not fail the workflow here.
  if [[ "${SKIP_RUNNER_DOCKER_CERTS_D:-0}" == "1" ]]; then
    echo "Skipping runner-side Docker certs.d install; ARC DinD sidecar owns daemon CA trust."
    return 0
  fi

  if [[ -d "$docker_certs_dir" && -w "$docker_certs_dir" ]]; then
    cp "$CERT_FILE" "$ca_dest"
    chmod 0644 "$ca_dest"
    echo "CA installed into runner-side Docker certs.d: $ca_dest"
    return 0
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo install -D -m 0644 "$CERT_FILE" "$ca_dest"
    echo "CA installed into runner-side Docker certs.d via sudo: $ca_dest"
    return 0
  fi

  echo "WARNING: Could not install CA into runner-side Docker certs.d at $ca_dest"
  echo "This is non-fatal when ARC DinD mounts the CA into the dind sidecar."
  return 0
}

install_into_runner_trust
install_into_docker_daemon_trust

# --- Patch BuildKit containers if builder name is provided ---
if [[ -n "${BUILDX_BUILDER_NAME:-}" ]]; then
  echo ""
  echo "Patching BuildKit containers for builder: $BUILDX_BUILDER_NAME"
  
  # Ensure builder is bootstrapped
  docker buildx inspect "$BUILDX_BUILDER_NAME" --bootstrap
  
  # Find BuildKit containers
  CONTAINERS=$(docker ps --format '{{.Names}}' | grep -E "^buildx_buildkit_${BUILDX_BUILDER_NAME}" || true)
  
  if [[ -z "$CONTAINERS" ]]; then
    echo "ERROR: No BuildKit containers found for builder '$BUILDX_BUILDER_NAME'."
    echo "docker/build-push-action uses BuildKit containers that must trust the CA."
    exit 4
  fi
  
  echo "Found BuildKit containers:"
  echo "$CONTAINERS"
  echo ""
  
  for container in $CONTAINERS; do
    echo "Patching $container..."

    docker cp "$CERT_FILE" "${container}:/tmp/spbnix-harbor-ca.crt"

    if docker exec "$container" sh -lc 'command -v update-ca-certificates >/dev/null 2>&1'; then
      docker exec "$container" sh -lc '
        set -eu
        mkdir -p /usr/local/share/ca-certificates
        cp /tmp/spbnix-harbor-ca.crt /usr/local/share/ca-certificates/spbnix-harbor-ca.crt
        update-ca-certificates
      '
    else
      echo "WARNING: update-ca-certificates not available in $container, appending to system CA bundle"
      docker exec "$container" sh -lc '
        set -eu
        test -f /etc/ssl/certs/ca-certificates.crt
        cat /tmp/spbnix-harbor-ca.crt >> /etc/ssl/certs/ca-certificates.crt
      ' || {
        echo "ERROR: Failed to install CA in BuildKit container $container"
        exit 4
      }
    fi

    docker exec "$container" sh -lc '
      test -s /etc/ssl/certs/ca-certificates.crt
      grep -q "BEGIN CERTIFICATE" /etc/ssl/certs/ca-certificates.crt
    '

    echo "Patched: $container"
  done
  
  echo ""
  echo "BuildKit containers patched successfully"
fi

echo ""
echo "SPbNIX Harbor CA installation complete"
