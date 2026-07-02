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
#   BUILDX_BUILDER_NAME  - Buildx builder name (overrides positional arg)
#   BUILDKITD_CONFIG    - Path to buildkitd.toml for Harbor CA trust
#   K9B_BUILDX_DRIVER   - Buildx driver (default: docker-container)
#   K9B_BUILDKIT_IMAGE  - BuildKit image (default: Harbor proxy-cache)
#
# Outputs:
#   Writes builder name to $GITHUB_OUTPUT if set:
#     name=<builder>
#     builder_name=<builder>
#
#   Exports to $GITHUB_ENV:
#     K9B_BUILDX_BUILDER=<builder>
#
# Requirements:
#   - Docker must be available
#   - Docker Buildx plugin must be installed
#   - Uses Harbor proxy-cache for BuildKit image
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

# Builder name: env var takes precedence, then positional arg, then default
BUILDER_NAME="${BUILDX_BUILDER_NAME:-${1:-k9b-harbor-builder}}"
BUILDX_DRIVER="${K9B_BUILDX_DRIVER:-docker-container}"
BUILDKIT_IMAGE="${K9B_BUILDKIT_IMAGE:-harbor-pve1.spbnix.local/dockerhub-cache/moby/buildkit:buildx-stable-1}"
# Support both BUILDKITD_CONFIG (preferred) and K9B_BUILDKIT_CONFIG (legacy)
BUILDKIT_CONFIG="${BUILDKITD_CONFIG:-${K9B_BUILDKIT_CONFIG:-}}"

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

# Validate BuildKit config if provided
if [[ -n "${BUILDKIT_CONFIG}" ]]; then
    if [[ ! -f "${BUILDKIT_CONFIG}" ]]; then
        echo "ERROR: BuildKit config does not exist: ${BUILDKIT_CONFIG}"
        exit 1
    fi
    echo "BuildKit config: ${BUILDKIT_CONFIG}"
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

# Export builder name for provenance and other steps
if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "K9B_BUILDX_BUILDER=${BUILDER_NAME}" >> "${GITHUB_ENV}"
fi

echo "Buildx builder setup complete: ${BUILDER_NAME}"
