#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Login to Docker registry using explicit shell command.
# Replaces docker/login-action with native shell.
#
# Usage:
#   source scripts/ci/docker_login.sh <registry> <username> <password_env_var>
#
# The password is read from the environment variable specified.
# This avoids echoing secrets in logs.
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

REGISTRY="${1:-}"
USERNAME="${2:-}"
PASSWORD_VAR="${3:-}"

if [[ -z "${REGISTRY}" ]] || [[ -z "${USERNAME}" ]] || [[ -z "${PASSWORD_VAR}" ]]; then
    echo "ERROR: Missing required arguments"
    echo "Usage: docker_login.sh <registry> <username> <password_env_var>"
    exit 1
fi

# Get password from environment variable
PASSWORD="${!PASSWORD_VAR:-}"
if [[ -z "${PASSWORD}" ]]; then
    echo "ERROR: ${PASSWORD_VAR} is not set or empty"
    exit 1
fi

echo "=== Docker login to ${REGISTRY} ==="
echo "Username: ${USERNAME}"
echo "Registry: ${REGISTRY}"

# Login using password-stdin (avoids echoing password)
printf '%s' "${PASSWORD}" | docker login "${REGISTRY}" \
    --username "${USERNAME}" \
    --password-stdin

echo "=== Docker login complete ==="
