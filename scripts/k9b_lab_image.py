"""Helper for building and pushing k9b images to Harbor registry.

This module provides functions for building k9b images and pushing them
to the Harbor registry for use in live lab deployments.

The key contract is:
1. Build the k9b-backend image with a unique per-run tag
2. Push to Harbor so it's available to K3s cluster nodes
3. Return the image reference to pass to the baseline installer

Usage:
    from scripts.k9b_lab_image import build_and_push_k9b_backend_image

    image_ref = build_and_push_k9b_image(
        tag="otel-live-123-1-abc123def456",
        push=True,
    )
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

# Harbor registry configuration
HARBOR_REGISTRY = "harbor-pve1.spbnix.local"
HARBOR_PROJECT = "k9b"
BACKEND_IMAGE_NAME = "k9b-backend"


@dataclass
class ImageBuildResult:
    """Result of a build-and-push operation."""

    repository: str
    tag: str
    image_ref: str
    digest: str | None = None
    success: bool = False
    error: str | None = None


def generate_live_lab_tag(
    run_id: str | None = None,
    run_attempt: str | None = None,
    sha: str | None = None,
    prefix: str = "otel-live",
) -> str:
    """Generate a unique immutable tag for live lab images.

    Args:
        run_id: GitHub run ID (from GITHUB_RUN_ID env)
        run_attempt: GitHub run attempt (from GITHUB_RUN_ATTEMPT env)
        sha: Git commit SHA (from GITHUB_SHA env)
        prefix: Tag prefix (default: "otel-live")

    Returns:
        Unique tag string in format: {prefix}-{run_id}-{attempt}-{sha12}
    """
    run_id = run_id or os.environ.get("GITHUB_RUN_ID", "local")
    run_attempt = run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    sha = sha or os.environ.get("GITHUB_SHA", "dev")
    # Use first 12 chars of SHA for brevity
    sha_short = sha[:12] if len(sha) >= 12 else sha
    return f"{prefix}-{run_id}-{run_attempt}-{sha_short}"


def build_and_push_k9b_backend_image(
    tag: str,
    push: bool = True,
    dockerfile: str = "./Dockerfile.python",
    build_args: dict[str, str] | None = None,
) -> ImageBuildResult:
    """Build and optionally push k9b-backend image to Harbor.

    Args:
        tag: Image tag (e.g., "otel-live-123-1-abc123def456")
        push: Whether to push to registry (default: True)
        dockerfile: Path to Dockerfile (default: ./Dockerfile.python)
        build_args: Additional build args (e.g., {"KUBECTL_VERSION": "v1.29.6"})

    Returns:
        ImageBuildResult with repository, tag, image_ref, digest, and status
    """
    repository = f"{HARBOR_REGISTRY}/{HARBOR_PROJECT}/{BACKEND_IMAGE_NAME}"
    image_ref = f"{repository}:{tag}"

    build_args = build_args or {}

    cmd = [
        "docker", "build",
        "-t", image_ref,
        "-f", dockerfile,
    ]

    # Add build args
    for key, value in build_args.items():
        cmd.extend(["--build-arg", f"{key}={value}"])

    # Add context (current directory)
    cmd.append(".")

    print(f"Building k9b-backend image: {image_ref}")
    print(f"Dockerfile: {dockerfile}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        return ImageBuildResult(
            repository=repository,
            tag=tag,
            image_ref=image_ref,
            success=False,
            error=f"Docker build failed: {e.stderr}",
        )

    # Push if requested
    digest = None
    if push:
        print(f"Pushing image to Harbor: {image_ref}")
        try:
            push_result = subprocess.run(
                ["docker", "push", image_ref],
                check=True,
                capture_output=True,
                text=True,
            )
            print(push_result.stdout)

            # Extract digest from push output
            digest = _extract_digest_from_push(push_result.stdout, image_ref)

        except subprocess.CalledProcessError as e:
            return ImageBuildResult(
                repository=repository,
                tag=tag,
                image_ref=image_ref,
                success=False,
                error=f"Docker push failed: {e.stderr}",
            )

    return ImageBuildResult(
        repository=repository,
        tag=tag,
        image_ref=image_ref,
        digest=digest,
        success=True,
    )


def _extract_digest_from_push(output: str, image_ref: str) -> str | None:
    """Extract digest from docker push output.

    Looks for sha256:... pattern in push output.
    """
    import re

    # Look for digest pattern in push output
    digest_pattern = r"sha256:([a-f0-9]{64})"
    matches = re.findall(digest_pattern, output)
    if matches:
        return f"sha256:{matches[0]}"

    # Also check for digest in the image reference format
    digest_pattern2 = f"{re.escape(image_ref)}@sha256:([a-f0-9]{{64}})"
    matches2 = re.findall(digest_pattern2, output)
    if matches2:
        return f"sha256:{matches2[0]}"

    return None


def parse_image_ref(image_ref: str) -> tuple[str, str]:
    """Parse image reference into repository and tag.

    Args:
        image_ref: Full image reference (e.g., "harbor.example.com/k9b/k9b-backend:tag")

    Returns:
        Tuple of (repository, tag)
    """
    if ":" not in image_ref:
        return image_ref, "latest"

    # Split on last colon (handle port numbers like localhost:5000/image:tag)
    last_colon = image_ref.rfind(":")
    if last_colon == -1:
        return image_ref, "latest"

    repository = image_ref[:last_colon]
    tag = image_ref[last_colon + 1:]

    return repository, tag


def main() -> None:
    """CLI entry point for building k9b images."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Build and push k9b backend image to Harbor"
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Image tag (default: auto-generated from run ID)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Build only, do not push to registry",
    )
    parser.add_argument(
        "--dockerfile",
        default="./Dockerfile.python",
        help="Path to Dockerfile",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    # Generate tag if not provided
    tag = args.tag or generate_live_lab_tag()

    result = build_and_push_k9b_backend_image(
        tag=tag,
        push=not args.no_push,
        dockerfile=args.dockerfile,
    )

    if args.json:
        output = {
            "repository": result.repository,
            "tag": result.tag,
            "image_ref": result.image_ref,
            "digest": result.digest,
            "success": result.success,
            "error": result.error,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.success:
            print(f"SUCCESS: Built and pushed {result.image_ref}")
            if result.digest:
                print(f"Digest: {result.digest}")
        else:
            print(f"FAILED: {result.error}")
            import sys
            sys.exit(1)


if __name__ == "__main__":
    main()
