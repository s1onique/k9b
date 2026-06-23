#!/usr/bin/env python3
"""Image preflight CLI shim for CNPG Live Lab.

This is a thin CLI wrapper that delegates to modular preflight components:
- k9b_cnpg_image_preflight_registry: Registry manifest availability
- k9b_cnpg_image_preflight_node: Node-side pullability via diagnostic pods
- k9b_cnpg_image_preflight_types: Shared types and failure constants

Usage:
    python k9b_cnpg_image_preflight.py resolved-images \
        --backend-image <ref> --frontend-image <ref> --artifact-dir <path>

    python k9b_cnpg_image_preflight.py registry-preflight \
        --backend-image <ref> --frontend-image <ref> \
        --registry-username <user> --registry-password <pass> \
        --artifact-dir <path>

    python k9b_cnpg_image_preflight.py node-pull-preflight \
        --kubeconfig <path> --namespace <name> \
        --backend-image <ref> --frontend-image <ref> \
        --artifact-dir <path>

    python k9b_cnpg_image_preflight.py check-image-pull-secrets \
        --kubeconfig <path> --namespace <name> --artifact-dir <path>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from k9b_cnpg_image_preflight_registry import check_manifest_with_curl
from k9b_cnpg_image_preflight_node import check_node_pullability
from k9b_cnpg_image_preflight_types import (
    FAIL_IMAGE_CREDS_MISSING,
    FAIL_IMAGE_FORBIDDEN,
    FAIL_IMAGE_MISSING,
    FAIL_IMAGE_NETWORK,
    FAIL_IMAGE_TLS,
    FAIL_IMAGE_UNAUTHORIZED,
    FAIL_IMAGE_UNKNOWN,
    FAIL_IMAGE_UNRESOLVED,
    ImagePullSecretStatus,
    RegistryResult,
)


def log(msg: str) -> None:
    """Log info message."""
    print(f"[image-preflight] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[image-preflight] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[image-preflight] ERROR: {msg}", file=sys.stderr, flush=True)


def write_json_atomically(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def _validate_image_ref(image_ref: str, component: str) -> tuple[bool, dict | None]:
    """Validate image ref is non-empty. Returns (valid, error_result)."""
    if not image_ref or not image_ref.strip():
        return False, {
            "component": component,
            "image_ref": image_ref,
            "success": False,
            "failure_class": "image_ref_unresolved",
            "error_message": f"Empty {component} image ref provided",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    return True, None


def cmd_resolved_images(backend_image: str, frontend_image: str, artifact_dir: Path) -> int:
    """Write resolved image refs artifact. Fails if either image ref is empty."""
    from k9b_cnpg_image_preflight_types import FAIL_IMAGE_UNRESOLVED

    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Validate both image refs
    backend_valid, backend_error = _validate_image_ref(backend_image, "backend")
    frontend_valid, frontend_error = _validate_image_ref(frontend_image, "frontend")

    errors = []
    if not backend_valid and backend_error:
        errors.append(backend_error)
    if not frontend_valid and frontend_error:
        errors.append(frontend_error)

    if errors:
        error(f"Empty image refs are not allowed:")
        for e in errors:
            error(f"  {e['component']}: {e['error_message']}")
        # Write error artifact
        combined = {
            "timestamp": datetime.now(UTC).isoformat(),
            "success": False,
            "failure_classes": [FAIL_IMAGE_UNRESOLVED],
            "errors": errors,
        }
        write_json_atomically(out_dir / "resolved-images.json", combined)
        return 2

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "success": True,
        "images": {
            "backend": {
                "image_ref": backend_image,
                "component": "backend",
            },
            "frontend": {
                "image_ref": frontend_image,
                "component": "frontend",
            },
        },
    }

    out_path = out_dir / "resolved-images.json"
    write_json_atomically(out_path, data)
    log(f"Wrote resolved images to {out_path}")
    return 0


def cmd_registry_preflight(
    backend_image: str,
    frontend_image: str,
    registry_username: str | None,
    registry_password: str | None,
    artifact_dir: Path,
) -> int:
    """Check registry manifest availability for both images."""
    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_success = True
    failure_classes = []

    for image_ref, component in [(backend_image, "backend"), (frontend_image, "frontend")]:
        log(f"Checking registry manifest: {image_ref}")
        result = check_manifest_with_curl(image_ref, registry_username, registry_password)
        results.append(result)

        # Write individual result
        write_json_atomically(out_dir / f"registry-{component}.json", result)

        if not result.get("success", False):
            all_success = False
            fc = result.get("failure_class", "")
            if fc:
                failure_classes.append(fc)

    # Write combined result
    combined = {
        "timestamp": datetime.now(UTC).isoformat(),
        "results": results,
        "all_success": all_success,
        "failure_classes": failure_classes,
    }
    write_json_atomically(out_dir / "registry-preflight.json", combined)

    if all_success:
        log("Registry preflight PASSED for all images")
        return 0

    # Determine exit code based on failure class
    for fc in failure_classes:
        if fc in (FAIL_IMAGE_MISSING, FAIL_IMAGE_UNAUTHORIZED, FAIL_IMAGE_FORBIDDEN):
            return 2  # Fatal - image not available
        if fc in (FAIL_IMAGE_CREDS_MISSING, FAIL_IMAGE_TLS, FAIL_IMAGE_NETWORK):
            return 3  # Configuration error
        if fc == FAIL_IMAGE_UNKNOWN:
            return 4  # Unknown error

    return 1


def cmd_node_pull_preflight(
    kubeconfig: str,
    namespace: str,
    backend_image: str,
    frontend_image: str,
    artifact_dir: Path,
) -> int:
    """Test node-side image pullability for both images."""
    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_success = True
    failure_classes = []

    for image_ref, component in [(backend_image, "backend"), (frontend_image, "frontend")]:
        log(f"Testing node pullability: {image_ref}")
        result = check_node_pullability(
            kubeconfig=kubeconfig,
            namespace=namespace,
            image_ref=image_ref,
            component=component,
            artifact_dir=out_dir,
        )
        results.append(result)

        # Write individual result
        write_json_atomically(out_dir / f"node-pull-{component}.json", result)

        if not result.get("success", False):
            all_success = False
            fc = result.get("failure_class", "")
            if fc:
                failure_classes.append(fc)

    # Write combined result
    combined = {
        "timestamp": datetime.now(UTC).isoformat(),
        "results": results,
        "all_success": all_success,
        "failure_classes": failure_classes,
    }
    write_json_atomically(out_dir / "node-pull-preflight.json", combined)

    if all_success:
        log("Node pull preflight PASSED for all images")
        return 0

    return 1  # Node pull failure


def cmd_check_image_pull_secrets(kubeconfig: str, namespace: str, artifact_dir: Path) -> int:
    """Check imagePullSecrets status in namespace."""
    import subprocess

    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "kubectl",
            "--kubeconfig", kubeconfig,
            "-n", namespace,
            "get", "serviceaccount", "default", "-o", "json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        status = ImagePullSecretStatus(
            namespace=namespace,
            secrets_exist=False,
            error_message=f"Failed to get serviceaccount: {result.stderr}",
        )
    else:
        sa_data = json.loads(result.stdout)
        secret_names = [
            s.get("name", "")
            for s in sa_data.get("imagePullSecrets", [])
            if s.get("name")
        ]
        status = ImagePullSecretStatus(
            namespace=namespace,
            secrets_exist=len(secret_names) > 0,
            secret_names=secret_names,
            has_service_account_ref=len(secret_names) > 0,
            service_account_name=sa_data.get("metadata", {}).get("name", "default"),
        )

    write_json_atomically(out_dir / "image-pull-secret.json", status.to_dict())
    log(f"ImagePullSecrets status: secrets_exist={status.secrets_exist}, names={status.secret_names}")
    return 0


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Image preflight diagnostics for CNPG Live Lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # resolved-images
    p_resolved = subparsers.add_parser("resolved-images", help="Write resolved image refs")
    p_resolved.add_argument("--backend-image", required=True)
    p_resolved.add_argument("--frontend-image", required=True)
    p_resolved.add_argument("--artifact-dir", required=True, type=Path)

    # registry-preflight
    p_reg = subparsers.add_parser("registry-preflight", help="Check registry manifest availability")
    p_reg.add_argument("--backend-image", required=True)
    p_reg.add_argument("--frontend-image", required=True)
    p_reg.add_argument("--registry-username", default=None)
    p_reg.add_argument("--registry-password", default=None)
    p_reg.add_argument("--artifact-dir", required=True, type=Path)

    # node-pull-preflight
    p_node = subparsers.add_parser("node-pull-preflight", help="Test node-side image pullability")
    p_node.add_argument("--kubeconfig", required=True)
    p_node.add_argument("--namespace", required=True)
    p_node.add_argument("--backend-image", required=True)
    p_node.add_argument("--frontend-image", required=True)
    p_node.add_argument("--artifact-dir", required=True, type=Path)

    # check-image-pull-secrets
    p_secrets = subparsers.add_parser("check-image-pull-secrets", help="Check imagePullSecrets status")
    p_secrets.add_argument("--kubeconfig", required=True)
    p_secrets.add_argument("--namespace", required=True)
    p_secrets.add_argument("--artifact-dir", required=True, type=Path)

    args = parser.parse_args()

    match args.command:
        case "resolved-images":
            return cmd_resolved_images(args.backend_image, args.frontend_image, args.artifact_dir)
        case "registry-preflight":
            return cmd_registry_preflight(
                args.backend_image, args.frontend_image,
                args.registry_username, args.registry_password, args.artifact_dir,
            )
        case "node-pull-preflight":
            return cmd_node_pull_preflight(
                args.kubeconfig, args.namespace,
                args.backend_image, args.frontend_image, args.artifact_dir,
            )
        case "check-image-pull-secrets":
            return cmd_check_image_pull_secrets(args.kubeconfig, args.namespace, args.artifact_dir)
        case _:
            error(f"Unknown command: {args.command}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
