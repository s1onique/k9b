#!/usr/bin/env python3
"""Verify authorization record integrity from downloaded artifact.

Verifies:
- Exactly one JSON file exists
- Record has required fields
- SHA-256 matches computed digest
- Image refs are valid format
- Scheduler == Backend digest

All GitHub API calls receive token via GH_TOKEN env variable.
"""
import hashlib
import json
import sys
from pathlib import Path


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


REQUIRED_FIELDS = (
    "schema_version",
    "authorization_status",
    "subject_sha",
    "upstream_run_id",
    "upstream_run_attempt",
    "current_main_sha",
    "backend_image_ref",
    "scheduler_image_ref",
    "frontend_image_ref",
    "record_sha256",
)

IMAGE_PATTERN = r"^[^\s@]+@sha256:[0-9a-f]{64}$"


def main() -> None:
    errors: list[str] = []

    # Find exactly one JSON file
    paths = list(Path("artifacts/auth_extracted").glob("*.json"))
    if len(paths) == 0:
        print("FATAL: no JSON in auth artifact")
        sys.exit(1)
    if len(paths) > 1:
        print("FATAL: multiple JSON files in auth artifact")
        sys.exit(1)

    record_path = paths[0]
    try:
        data = json.loads(record_path.read_text())
    except json.JSONDecodeError as e:
        print(f"FATAL: invalid JSON: {e}")
        sys.exit(1)

    # Verify digest
    actual_sha = compute_sha256(record_path)
    expected_sha = data.get("record_sha256", "")
    if actual_sha != expected_sha:
        errors.append(f"record SHA mismatch: expected {expected_sha}, got {actual_sha}")

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    # Validate authorization status
    auth_status = data.get("authorization_status", "")
    if auth_status not in ("authorized", "stale_upstream", "identity_unavailable"):
        errors.append(f"invalid authorization_status: {auth_status}")

    if auth_status == "authorized":
        # Validate image refs format
        import re

        pattern = re.compile(IMAGE_PATTERN)
        for label in ("backend", "scheduler", "frontend"):
            ref = data.get(f"{label}_image_ref", "")
            if not pattern.match(ref):
                errors.append(f"malformed {label}_image_ref: {ref}")

        # Verify scheduler == backend
        if data.get("scheduler_image_ref") != data.get("backend_image_ref"):
            errors.append("scheduler_image_ref != backend_image_ref")

    if errors:
        for err in errors:
            print(f"FATAL: {err}")
        sys.exit(1)

    print(f"RECORD_VALID=PASS status={auth_status}")


if __name__ == "__main__":
    main()
