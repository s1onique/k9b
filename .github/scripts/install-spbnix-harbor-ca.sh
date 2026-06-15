#!/usr/bin/env bash
# install-spbnix-harbor-ca.sh
# Installs SPbNIX Harbor CA certificate into runner and BuildKit containers.
#
# Required env vars:
#   SPBNIX_CA_CERT_PEM  - PEM-encoded CA certificate content
#
# Optional env vars:
#   BUILDX_BUILDER_NAME - Buildx builder name; if set, patches BuildKit containers
#
set -euo pipefail

# --- Require CA certificate ---
if [[ -z "${SPBNIX_CA_CERT_PEM:-}" ]]; then
  echo "ERROR: SPBNIX_CA_CERT_PEM environment variable is not set."
  echo "Please set SPBNIX_CA_CERT_PEM to the PEM-encoded CA certificate content."
  exit 1
fi

# --- Setup directories ---
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

# --- Install into runner trust ---
install_into_runner() {
  echo "Installing CA into runner trust store..."

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
        echo "Neither /usr/local/share/ca-certificates nor /etc/ssl/certs/ca-certificates.crt are writable."
        echo "Docker login/push diagnostics require trustworthy TLS."
        exit 1
      fi
    fi
    echo "CA installed into runner trust: $dest"
  else
    echo "ERROR: Cannot install CA into runner trust: no write access to system CA store."
    echo "Neither /usr/local/share/ca-certificates nor /etc/ssl/certs/ca-certificates.crt are writable."
    echo "Docker login/push diagnostics require trustworthy TLS."
    exit 1
  fi
}

install_into_runner

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
