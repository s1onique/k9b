#!/usr/bin/env python3
"""Strict record schema and immutable image contract validator.

Usage:
    validate-record.py <expected_upstream_sha>

All values passed via argv/env to avoid GitHub expression syntax in source.
"""
import re
import sys
from pathlib import Path

# Strict constants
CANONICAL_REGISTRY = "harbor-pve1.spbnix.local"
CANONICAL_PROJECT = "k9b"
IMAGE_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
VALID_IMAGE_CLASS = "experimental-lab"
VALID_RUNTIME_GATE = "pass"

REQUIRED_FIELDS = frozenset((
    "schema_version",
    "image_class",
    "subject_sha",
    "runtime_gate",
    "backend_image_ref",
    "scheduler_image_ref",
    "frontend_image_ref",
    "scheduler_uses_backend_image",
    "full_verify_remains_authoritative",
    "ready_for_image_publication",
    "ready_for_production_deployment",
    "ready_for_live_acceptance",
))

APPROVED_REPOS = frozenset((
    "harbor-pve1.spbnix.local/k9b/k9b-backend",
    "harbor-pve1.spbnix.local/k9b/k9b-frontend",
))


def strict_parse(path: Path) -> tuple[dict[str, object], list[str]]:
    """Parse JSON with strict validation.

    Returns (data, errors).
    """
    errors: list[str] = []
    try:
        content = path.read_text()
    except Exception as e:
        return {}, [f"cannot read file: {e}"]

    # Check for duplicate keys (simple check via regex)
    import json as _json
    try:
        data = _json.loads(content)
    except _json.JSONDecodeError as e:
        return {}, [f"invalid JSON: {e}"]

    if not isinstance(data, dict):
        return {}, ["root must be object"]

    # Check for unknown fields
    unknown = set(data.keys()) - REQUIRED_FIELDS
    if unknown:
        errors.append(f"unknown fields: {', '.join(sorted(unknown))}")

    # Check for missing required fields
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"missing required fields: {', '.join(sorted(missing))}")

    # Type checks
    if not isinstance(data.get("image_class"), str):
        errors.append("image_class must be string")
    if not isinstance(data.get("subject_sha"), str):
        errors.append("subject_sha must be string")
    if not isinstance(data.get("runtime_gate"), str):
        errors.append("runtime_gate must be string")
    if not isinstance(data.get("scheduler_uses_backend_image"), bool):
        errors.append("scheduler_uses_backend_image must be boolean")
    if not isinstance(data.get("full_verify_remains_authoritative"), bool):
        errors.append("full_verify_remains_authoritative must be boolean")

    for field in ("ready_for_image_publication", "ready_for_production_deployment",
                  "ready_for_live_acceptance"):
        val = data.get(field)
        if not isinstance(val, bool):
            errors.append(f"{field} must be boolean")

    # Value validation
    if data.get("image_class") != VALID_IMAGE_CLASS:
        errors.append(f"image_class must be '{VALID_IMAGE_CLASS}'")
    if data.get("runtime_gate") != VALID_RUNTIME_GATE:
        errors.append(f"runtime_gate must be '{VALID_RUNTIME_GATE}'")
    if data.get("scheduler_uses_backend_image") is not True:
        errors.append("scheduler_uses_backend_image must be true")
    if data.get("full_verify_remains_authoritative") is not True:
        errors.append("full_verify_remains_authoritative must be true")

    # Boolean fields must be false
    for field in ("ready_for_image_publication", "ready_for_production_deployment",
                  "ready_for_live_acceptance"):
        if data.get(field) is not False:
            errors.append(f"{field} must be false")

    # SHA format check
    sha = data.get("subject_sha", "")
    if not re.match(r"^[0-9a-f]{40}$", sha):
        errors.append(f"invalid subject_sha format: {sha}")

    # Image ref format and content validation
    for label in ("backend", "scheduler", "frontend"):
        ref = data.get(f"{label}_image_ref", "")
        if not isinstance(ref, str):
            errors.append(f"{label}_image_ref must be string")
            continue
        if not IMAGE_PATTERN.match(ref):
            errors.append(f"malformed {label}_image_ref: {ref}")
        else:
            repo = ref.split("@")[0]
            if repo not in APPROVED_REPOS:
                errors.append(f"unapproved repository for {label}: {repo}")

    # Scheduler == Backend digest
    backend_ref = data.get("backend_image_ref", "")
    scheduler_ref = data.get("scheduler_image_ref", "")
    if backend_ref and scheduler_ref:
        if backend_ref != scheduler_ref:
            errors.append("scheduler_image_ref != backend_image_ref")

    return data, errors


def main() -> None:
    if len(sys.argv) != 2:
        print("FATAL: wrong number of arguments", file=sys.stderr)
        sys.exit(1)

    expected_sha = sys.argv[1]

    paths = list(Path("artifacts/record_extracted").glob("*.json"))
    if len(paths) == 0:
        print("FATAL: no JSON in artifact")
        sys.exit(1)
    if len(paths) > 1:
        print("FATAL: multiple JSON files in artifact")
        sys.exit(1)

    record_path = paths[0]
    data, errors = strict_parse(record_path)

    # Additional upstream SHA check
    if data.get("subject_sha") != expected_sha:
        errors.append(f"subject_sha mismatch: expected {expected_sha}")

    if errors:
        for e in errors:
            print(f"FATAL: {e}")
        sys.exit(1)

    # Emit outputs
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"backend_image_ref={data['backend_image_ref']}\n")
        f.write(f"scheduler_image_ref={data['scheduler_image_ref']}\n")
        f.write(f"frontend_image_ref={data['frontend_image_ref']}\n")

    print("SCHEMA_AND_IMAGE_CONTRACT=PASS")


if __name__ == "__main__":
    import os
    main()
