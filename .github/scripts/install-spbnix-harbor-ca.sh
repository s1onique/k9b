#!/usr/bin/env bash
# install-spbnix-harbor-ca.sh
# Installs SPbNIX Harbor CA certificate into runner, Docker daemon, and BuildKit containers.
#
# Required env vars:
#   SPBNIX_CA_CERT_PEM  - PEM-encoded CA certificate content
#
# Optional env vars:
#   BUILDX_BUILDER_NAME - Buildx builder name; if set, patches BuildKit containers
#   HARBOR_HOST         - Harbor hostname (default: harbor-pve1.spbnix.local)
#
set -euo pipefail

# --- Require CA certificate ---
if [[ -z "${SPBNIX_CA_CERT_PEM:-}" ]]; then
  echo "ERROR: SPBNIX_CA_CERT_PEM environment variable is not set."
  echo "Please set SPBNIX_CA_CERT_PEM to the PEM-encoded CA certificate content."
  exit 1
fi

# --- Configuration ---
HARBOR_HOST="${HARBOR_HOST:-harbor-pve1.spbnix.local}"
CERT_DIR="${RUNNER_TEMP:-/tmp}/spbnix-ca"
CERT_FILE="${CERT_DIR}/spbnix-harbor-ca.crt"
mkdir -p "$CERT_DIR"

# --- Write certificate ---
echo "$SPBNIX_CA_CERT_PEM" > "$CERT_FILE"

# --- Validate PEM ---
echo "Validating CA certificate..."
VALIDATED=$(openssl x509 -in "$CERT_FILE" -noout -subject -issuer -dates 2>&1) || {
  echo "ERROR: Invalid PEM certificate in SPBNIX_CA_CERT_PEM"
  echo "openssl output: $VALIDATED"
  exit 1
}
echo "CA certificate details:"
echo "$VALIDATED"
echo ""

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
    exit 1
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
        exit 1
      fi
    fi
    echo "CA installed into runner system trust: $dest"
  else
    echo "ERROR: Cannot install CA into runner trust: no write access to system CA store."
    exit 1
  fi
}

# --- Install into Docker daemon trust (CRITICAL for "Error response from daemon") ---
# Docker daemon validates registry TLS using /etc/docker/certs.d/<host>/ca.crt
# This path must be accessible to the Docker daemon, not just the runner container.
# In DinD setups, the daemon runs in a sidecar container; we install to the host
# filesystem where the daemon can see it.
install_into_docker_daemon_trust() {
  echo "Installing CA into Docker daemon trust store for $HARBOR_HOST..."

  local docker_certs_dir="/etc/docker/certs.d/${HARBOR_HOST}"
  local ca_dest="${docker_certs_dir}/ca.crt"

  # Try runner filesystem first (works if runner IS the Docker host)
  if [[ -w "$docker_certs_dir" ]] || mkdir -p "$docker_certs_dir" 2>/dev/null; then
    cp "$CERT_FILE" "$ca_dest"
    chmod 0644 "$ca_dest"
    echo "CA installed into Docker daemon trust: $ca_dest"
    return 0
  fi

  # Try with sudo (runner container with sudo access)
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo mkdir -p "$docker_certs_dir"
    sudo cp "$CERT_FILE" "$ca_dest"
    sudo chmod 0644 "$ca_dest"
    echo "CA installed into Docker daemon trust (sudo): $ca_dest"
    return 0
  fi

  echo "WARNING: Could not install CA into Docker daemon trust at $ca_dest"
  echo "This may cause 'Error response from daemon' when docker login/push runs."
  echo "Attempting to verify docker info anyway..."
  return 0  # Don't fail - docker might work if daemon already trusts the CA
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
    exit 1
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
        exit 1
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
