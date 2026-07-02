#!/usr/bin/env bash
# CI-HERMETIC-TOOLCACHE:
# Wire QEMU/binfmt from Harbor-cached binfmt image.
#
# Usage:
#   scripts/ci/wire_qemu_binfmt.sh [platform]
#
# Arguments:
#   platform - QEMU platform to register (default: aarch64)
#
# Environment:
#   K9B_BINFMT_IMAGE - binfmt image (default: Harbor proxy-cache)
#
# Requirements:
#   - Docker must be available
#   - /proc/sys/fs/binfmt_misc must be accessible
#   - Uses Harbor proxy-cache: tonistiigi/binfmt
#
# See docs/ci-hermetic-toolchain.md

set -euo pipefail

PLATFORM="${1:-aarch64}"
BINFMT_IMAGE="${K9B_BINFMT_IMAGE:-harbor-pve1.spbnix.local/dockerhub-cache/tonistiigi/binfmt:latest}"

# Validate Docker availability
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is required for QEMU/binfmt setup"
    exit 1
fi

# Validate platform
if [[ "${PLATFORM}" != "aarch64" && "${PLATFORM}" != "arm64" ]]; then
    echo "ERROR: unsupported QEMU platform: ${PLATFORM}"
    echo "Supported platforms: aarch64, arm64"
    exit 1
fi

BINFMT_ENTRY="/proc/sys/fs/binfmt_misc/qemu-aarch64"

# Idempotent check: if already registered, print proof and exit
if [[ -f "${BINFMT_ENTRY}" ]]; then
    echo "QEMU aarch64 already registered with binfmt_misc:"
    cat "${BINFMT_ENTRY}"
    exit 0
fi

# Verify binfmt_misc filesystem is available
if [[ ! -d /proc/sys/fs/binfmt_misc ]]; then
    echo "ERROR: /proc/sys/fs/binfmt_misc is not available"
    echo "binfmt_misc kernel module may not be loaded"
    exit 1
fi

echo "Registering QEMU aarch64 with ${BINFMT_IMAGE}"
docker pull "${BINFMT_IMAGE}"
docker run --rm --privileged "${BINFMT_IMAGE}" --install aarch64

# Verify registration
if [[ -f "${BINFMT_ENTRY}" ]]; then
    echo "QEMU aarch64 registration successful:"
    cat "${BINFMT_ENTRY}"
else
    echo "WARNING: ${BINFMT_ENTRY} not visible after registration"
    echo "Docker may still work with QEMU for multi-arch builds"
fi
