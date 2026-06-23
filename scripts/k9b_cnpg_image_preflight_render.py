#!/usr/bin/env python3
"""Render Helm manifests and extract container images for preflight validation.

This module:
1. Renders Helm manifests using the exact same values/flags that will be used for install/upgrade
2. Extracts every container/initContainer image from rendered Pod templates
3. Writes rendered-images.json artifact
4. Compares rendered images against expected image refs

Usage:
    python k9b_cnpg_image_preflight_render.py render-and-compare \
        --chart <path> --release <name> --namespace <ns> \
        --values <values.yaml> [--set key=value ...] \
        --expected-backend <ref> --expected-frontend <ref> \
        --artifact-dir <path>
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Re-export failure classes for backward compatibility
from k9b_cnpg_image_preflight_types import (
    FAIL_IMAGE_PREFLIGHT_NO_RENDERED_IMAGES,
    FAIL_IMAGE_PREFLIGHT_RENDER_FAILED,
    FAIL_IMAGE_PREFLIGHT_RENDER_MISMATCH,
    ExtractedImage,
    ImageComparison,
    RenderedImages,
)
from k9b_cnpg_image_preflight_yaml import (
    extract_images_from_manifest,
    parse_yaml_documents,
)


def log(msg: str) -> None:
    """Log info message."""
    print(f"[image-preflight-render] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[image-preflight-render] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[image-preflight-render] ERROR: {msg}", file=sys.stderr, flush=True)


def write_json_atomically(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def render_helm_manifests(
    chart_path: str,
    release_name: str,
    namespace: str,
    values_files: list[str],
    set_values: list[str],
) -> tuple[str, str, int]:
    """Render Helm manifests using the specified values and --set overrides.

    Returns: (stdout, stderr, returncode)
    """
    cmd = [
        "helm", "template", release_name, chart_path,
        "--namespace", namespace,
    ]
    for values_file in values_files:
        cmd.extend(["--values", values_file])
    for set_value in set_values:
        cmd.extend(["--set", set_value])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", "helm template timed out after 120s", -1
    except FileNotFoundError:
        return "", "helm command not found", -1
    except Exception as e:
        return "", str(e), -1


def render_and_extract(
    chart_path: str,
    release_name: str,
    namespace: str,
    values_files: list[str],
    set_values: list[str],
) -> RenderedImages:
    """Render Helm manifests and extract all container images."""
    timestamp = datetime.now(UTC).isoformat()

    cmd_parts = [
        "helm", "template", release_name, chart_path,
        "--namespace", namespace,
    ]
    for values_file in values_files:
        cmd_parts.extend(["--values", values_file])
    for set_value in set_values:
        cmd_parts.extend(["--set", set_value])
    helm_command = " ".join(cmd_parts)

    log("Rendering Helm manifests...")
    log(f"Command: {helm_command}")

    stdout, stderr, rc = render_helm_manifests(
        chart_path, release_name, namespace, values_files, set_values
    )

    if rc != 0:
        log(f"Helm template failed with exit code {rc}")
        return RenderedImages(
            timestamp=timestamp,
            helm_command=helm_command,
            helm_stderr=stderr[:2000] if stderr else "",
            success=False,
            error_message=f"Helm template failed: {stderr[:500]}",
        )

    documents = parse_yaml_documents(stdout)
    log(f"Parsed {len(documents)} YAML documents")

    all_images: list[ExtractedImage] = []
    for doc in documents:
        images = extract_images_from_manifest(doc)
        all_images.extend(images)

    log(f"Extracted {len(all_images)} container images")
    for img in all_images:
        log(f"  - {img.resource_kind}/{img.resource_name}:{img.container_name} -> {img.image_ref}")

    return RenderedImages(
        timestamp=timestamp,
        helm_command=helm_command,
        helm_stderr=stderr[:500] if stderr else "",
        images=all_images,
        success=True,
    )


def compare_images(
    rendered: RenderedImages,
    expected_backend: str | None,
    expected_frontend: str | None,
) -> tuple[bool, list[ImageComparison], list[str]]:
    """Compare rendered images against expected image refs."""
    comparisons: list[ImageComparison] = []
    failure_messages: list[str] = []
    all_match = True

    rendered_backend = rendered.get_backend_image()
    backend_match = (rendered_backend == expected_backend) if expected_backend else (rendered_backend is not None)

    if expected_backend and rendered_backend != expected_backend:
        all_match = False
        failure_messages.append(
            f"FAILURE_CLASS={FAIL_IMAGE_PREFLIGHT_RENDER_MISMATCH}\n"
            f"EXPECTED_BACKEND={expected_backend}\n"
            f"RENDERED_BACKEND={rendered_backend or '(not found)'}"
        )

    comparisons.append(ImageComparison(
        component="backend",
        rendered_image=rendered_backend,
        expected_image=expected_backend,
        matches=backend_match,
    ))

    rendered_frontend = rendered.get_frontend_image()
    frontend_match = (rendered_frontend == expected_frontend) if expected_frontend else (rendered_frontend is not None)

    if expected_frontend and rendered_frontend != expected_frontend:
        all_match = False
        failure_messages.append(
            f"FAILURE_CLASS={FAIL_IMAGE_PREFLIGHT_RENDER_MISMATCH}\n"
            f"EXPECTED_FRONTEND={expected_frontend}\n"
            f"RENDERED_FRONTEND={rendered_frontend or '(not found)'}"
        )

    comparisons.append(ImageComparison(
        component="frontend",
        rendered_image=rendered_frontend,
        expected_image=expected_frontend,
        matches=frontend_match,
    ))

    return all_match, comparisons, failure_messages


def cmd_render(
    chart_path: str,
    release_name: str,
    namespace: str,
    values_files: list[str],
    set_values: list[str],
    artifact_dir: Path,
) -> int:
    """Execute render command."""
    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    rendered = render_and_extract(
        chart_path, release_name, namespace, values_files, set_values
    )

    out_path = out_dir / "rendered-images.json"
    write_json_atomically(out_path, rendered.to_dict())
    log(f"Wrote rendered images to {out_path}")

    if rendered.success:
        log(f"Render succeeded: {len(rendered.images)} images extracted")
        log(f"  Backend: {rendered.get_backend_image() or '(not found)'}")
        log(f"  Frontend: {rendered.get_frontend_image() or '(not found)'}")
        return 0
    else:
        log(f"Render failed: {rendered.error_message}")
        return 1


def cmd_compare(
    rendered_images_path: str,
    expected_backend: str | None,
    expected_frontend: str | None,
    artifact_dir: Path,
) -> int:
    """Execute compare command."""
    out_dir = Path(artifact_dir) / "image-preflight"
    rendered_path = Path(rendered_images_path)

    if not rendered_path.exists():
        error(f"Rendered images file not found: {rendered_images_path}")
        result = {
            "success": False,
            "failure_class": FAIL_IMAGE_PREFLIGHT_RENDER_FAILED,
            "error_message": f"Rendered images file not found: {rendered_images_path}",
        }
        write_json_atomically(out_dir / "image-preflight-compare.json", result)
        return 1

    with open(rendered_path) as f:
        data = json.load(f)

    images = [ExtractedImage(**img) for img in data.get("images", [])]
    rendered = RenderedImages(
        timestamp=data.get("timestamp", ""),
        helm_command=data.get("helm_command", ""),
        helm_stderr=data.get("helm_stderr", ""),
        images=images,
        success=data.get("success", True),
        error_message=data.get("error_message", ""),
    )

    all_match, comparisons, failure_messages = compare_images(
        rendered, expected_backend, expected_frontend
    )

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "success": all_match,
        "comparisons": [c.to_dict() for c in comparisons],
        "rendered_backend": rendered.get_backend_image(),
        "rendered_frontend": rendered.get_frontend_image(),
        "expected_backend": expected_backend,
        "expected_frontend": expected_frontend,
    }

    if not all_match:
        result["failure_class"] = FAIL_IMAGE_PREFLIGHT_RENDER_MISMATCH
        result["failure_messages"] = failure_messages

    write_json_atomically(out_dir / "image-preflight-compare.json", result)

    if all_match:
        log("Image comparison PASSED: rendered images match expected")
        log(f"  Backend: {rendered.get_backend_image()}")
        log(f"  Frontend: {rendered.get_frontend_image()}")
        return 0
    else:
        for msg in failure_messages:
            error(msg)
        log("Image comparison FAILED: rendered images do not match expected")
        return 2


def cmd_render_and_compare(
    chart_path: str,
    release_name: str,
    namespace: str,
    values_files: list[str],
    set_values: list[str],
    expected_backend: str | None,
    expected_frontend: str | None,
    artifact_dir: Path,
) -> int:
    """Execute combined render-and-compare command (used by workflow)."""
    out_dir = Path(artifact_dir) / "image-preflight"
    out_dir.mkdir(parents=True, exist_ok=True)

    rendered = render_and_extract(
        chart_path, release_name, namespace, values_files, set_values
    )

    rendered_path = out_dir / "rendered-images.json"
    write_json_atomically(rendered_path, rendered.to_dict())
    log(f"Wrote rendered images to {rendered_path}")

    if not rendered.success:
        error(f"Helm render failed: {rendered.error_message}")
        result = {
            "success": False,
            "failure_class": FAIL_IMAGE_PREFLIGHT_RENDER_FAILED,
            "error_message": rendered.error_message,
        }
        write_json_atomically(out_dir / "image-preflight-compare.json", result)
        return 1

    if not rendered.images:
        warn("No container images found in rendered manifests")
        result = {
            "success": False,
            "failure_class": FAIL_IMAGE_PREFLIGHT_NO_RENDERED_IMAGES,
            "error_message": "No container images found in rendered manifests",
        }
        write_json_atomically(out_dir / "image-preflight-compare.json", result)
        return 1

    all_match, comparisons, failure_messages = compare_images(
        rendered, expected_backend, expected_frontend
    )

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "success": all_match,
        "comparisons": [c.to_dict() for c in comparisons],
        "rendered_backend": rendered.get_backend_image(),
        "rendered_frontend": rendered.get_frontend_image(),
        "expected_backend": expected_backend,
        "expected_frontend": expected_frontend,
        "rendered_images_path": str(rendered_path),
    }

    if not all_match:
        result["failure_class"] = FAIL_IMAGE_PREFLIGHT_RENDER_MISMATCH
        result["failure_messages"] = failure_messages

    write_json_atomically(out_dir / "image-preflight-compare.json", result)

    if all_match:
        log("Image render-and-compare PASSED: rendered images match expected")
        log(f"  Backend: {rendered.get_backend_image()}")
        log(f"  Frontend: {rendered.get_frontend_image()}")
        return 0
    else:
        error("Image render-and-compare FAILED: rendered images do not match expected")
        error("NOT_PROCEEDING_WITH_HELM=true")
        for msg in failure_messages:
            error(msg)
        return 2


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Render Helm manifests and validate container images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_render = subparsers.add_parser("render", help="Render Helm manifests and extract images")
    p_render.add_argument("--chart", required=True)
    p_render.add_argument("--release", required=True)
    p_render.add_argument("--namespace", required=True)
    p_render.add_argument("--values", action="append", default=[])
    p_render.add_argument("--set", action="append", default=[], dest="set_values")
    p_render.add_argument("--artifact-dir", required=True, type=Path)

    p_compare = subparsers.add_parser("compare", help="Compare rendered images against expected")
    p_compare.add_argument("--rendered-images", required=True)
    p_compare.add_argument("--expected-backend", default=None)
    p_compare.add_argument("--expected-frontend", default=None)
    p_compare.add_argument("--artifact-dir", required=True, type=Path)

    p_rc = subparsers.add_parser("render-and-compare", help="Render and compare in one step")
    p_rc.add_argument("--chart", required=True)
    p_rc.add_argument("--release", required=True)
    p_rc.add_argument("--namespace", required=True)
    p_rc.add_argument("--values", action="append", default=[])
    p_rc.add_argument("--set", action="append", default=[], dest="set_values")
    p_rc.add_argument("--expected-backend", default=None)
    p_rc.add_argument("--expected-frontend", default=None)
    p_rc.add_argument("--artifact-dir", required=True, type=Path)

    args = parser.parse_args()

    match args.command:
        case "render":
            return cmd_render(args.chart, args.release, args.namespace,
                            args.values, args.set_values, args.artifact_dir)
        case "compare":
            return cmd_compare(args.rendered_images, args.expected_backend,
                             args.expected_frontend, args.artifact_dir)
        case "render-and-compare":
            return cmd_render_and_compare(args.chart, args.release, args.namespace,
                                         args.values, args.set_values,
                                         args.expected_backend, args.expected_frontend,
                                         args.artifact_dir)
        case _:
            error(f"Unknown command: {args.command}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
