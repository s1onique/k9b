#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire Docker Buildx builder using shell-first Docker CLI commands.
#
# Usage:
#   scripts/ci/wire_docker_buildx.sh [builder_name]
#
# Arguments:
#   builder_name - Buildx builder name (default: k9b-harbor-builder)
#
# Environment:
#   K9B_BUILDX_DRIVER       - Buildx driver (default: docker-container)
#   K9B_BUILDKIT_IMAGE     - BuildKit image (default: Harbor proxy-cache)
#   K9B_BUILDKIT_CONFIG    - Optional path to buildkitd.toml
#
# Outputs:
#   Writes builder name to $GITHUB_OUTPUT if set:
#     name=<builder>
#     builder_name=<builder>
#
# Requirements:
#   - Docker must be available
#   - Docker Buildx plugin must be installed
#   - Uses Harbor proxy-cache for BuildKit image
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

BUILDER_NAME="${1:-k9b-harbor-builder}"
BUILDX_DRIVER="${K9B_BUILDX_DRIVER:-docker-container}"
BUILDKIT_IMAGE="${K9B_BUILDKIT_IMAGE:-harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1}"
BUILDKIT_CONFIG="${K9B_BUILDKIT_CONFIG:-}"

# Validate Docker availability
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is required for Buildx setup"
    exit 1
fi

# Validate Buildx availability
if ! docker buildx version >/dev/null 2>&1; then
    echo "ERROR: docker buildx is required"
    echo "Install docker-buildx-plugin or upgrade Docker"
    exit 1
fi

echo "=== Docker Buildx setup ==="
echo "Builder: ${BUILDER_NAME}"
echo "Driver: ${BUILDX_DRIVER}"
echo "BuildKit image: ${BUILDKIT_IMAGE}"

# Idempotent: reuse existing builder if it exists
if docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
    echo "Builder ${BUILDER_NAME} already exists"
    docker buildx use "${BUILDER_NAME}"
else
    echo "Creating Buildx builder: ${BUILDER_NAME}"
    args=(
        buildx create
        --name "${BUILDER_NAME}"
        --driver "${BUILDX_DRIVER}"
        --driver-opt "image=${BUILDKIT_IMAGE}"
        --use
    )

    if [[ -n "${BUILDKIT_CONFIG}" ]]; then
        args+=(--buildkitd-config "${BUILDKIT_CONFIG}")
    fi

    docker "${args[@]}"
fi

# Ensure builder is active and print proof
docker buildx use "${BUILDER_NAME}"
docker buildx inspect "${BUILDER_NAME}" --bootstrap

# Write outputs for workflow steps
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
        echo "name=${BUILDER_NAME}"
        echo "builder_name=${BUILDER_NAME}"
    } >> "${GITHUB_OUTPUT}"
fi

echo "Buildx builder setup complete: ${BUILDER_NAME}"
