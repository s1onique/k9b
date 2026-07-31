#!/usr/bin/env python3
"""Authorization authority: record construction, atomic writes, checksum verification."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AuthorizationError(Exception):
    """Raised on authorization failure."""


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_authorization_record(
    record_sha256: str,
    current_main_sha: str,
    auth_status: str,
    backend_image_ref: str,
    scheduler_image_ref: str,
    frontend_image_ref: str,
    upstream_sha: str,
    upstream_run_id: str,
    upstream_run_attempt: str,
    bridge_sha: str,
    bridge_run_id: str,
    bridge_run_attempt: str,
    artifact_id: str,
    artifact_name: str,
    artifact_metadata_digest: str,
) -> Path:
    """Write authorization record and checksum sidecar atomically."""
    record = {
        "schema_version": "1.0",
        "authorization_status": auth_status,
        "subject_sha": upstream_sha,
        "upstream_run_id": upstream_run_id,
        "upstream_run_attempt": upstream_run_attempt,
        "current_main_sha": current_main_sha,
        "backend_image_ref": backend_image_ref,
        "scheduler_image_ref": scheduler_image_ref,
        "frontend_image_ref": frontend_image_ref,
        "record_sha256": record_sha256,
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "artifact_metadata_digest": artifact_metadata_digest,
        "bridge_sha": bridge_sha,
        "bridge_run_id": bridge_run_id,
        "bridge_run_attempt": bridge_run_attempt,
        "authorization_time": datetime.now(UTC).isoformat(),
    }

    output_path = Path("artifacts/experimental-lab-deploy-authorization.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2) + "\n")

    sidecar_path = Path("artifacts/experimental-lab-deploy-authorization.json.sha256")
    sidecar_path.write_text(compute_sha256(output_path) + "\n")

    return output_path


def verify_authorization_record(auth_dir: Path, current_main_sha: str) -> dict[str, Any]:
    """Verify authorization record and checksum sidecar."""
    json_paths = list(auth_dir.glob("experimental-lab-deploy-authorization.json"))
    sha_paths = list(auth_dir.glob("experimental-lab-deploy-authorization.json.sha256"))

    if not json_paths:
        raise AuthorizationError("No authorization JSON found")
    if not sha_paths:
        raise AuthorizationError("No checksum sidecar found")
    if len(json_paths) > 1:
        raise AuthorizationError("Multiple authorization JSON files")
    if len(sha_paths) > 1:
        raise AuthorizationError("Multiple checksum sidecar files")

    json_path = json_paths[0]
    sha_path = sha_paths[0]

    expected_sha = sha_path.read_text().strip()
    actual_sha = compute_sha256(json_path)
    if expected_sha != actual_sha:
        raise AuthorizationError(f"Checksum mismatch: expected {expected_sha}, got {actual_sha}")

    try:
        data = json.loads(json_path.read_text())
    except json.JSONDecodeError as e:
        raise AuthorizationError(f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise AuthorizationError("Root must be object")

    required_fields = (
        "schema_version", "authorization_status", "subject_sha",
        "upstream_run_id", "upstream_run_attempt", "current_main_sha",
        "backend_image_ref", "scheduler_image_ref", "frontend_image_ref",
        "record_sha256",
    )
    for field in required_fields:
        if field not in data:
            raise AuthorizationError(f"Missing required field: {field}")

    if data.get("current_main_sha") != current_main_sha:
        raise AuthorizationError(
            f"Main SHA mismatch: expected {current_main_sha}, "
            f"got {data.get('current_main_sha')}"
        )

    return data


def emit_outputs(data: dict[str, Any], output_path: str | None = None) -> None:
    """Emit GitHub outputs from authorization record."""
    if output_path is None:
        output_path = os.environ.get("GITHUB_OUTPUT", "/dev/null")
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"subject_sha={data['subject_sha']}\n")
        f.write(f"backend_image_ref={data['backend_image_ref']}\n")
        f.write(f"scheduler_image_ref={data['scheduler_image_ref']}\n")
        f.write(f"frontend_image_ref={data['frontend_image_ref']}\n")
        f.write(f"artifact_digest={data.get('artifact_metadata_digest', '')}\n")
        f.write(f"upstream_run_id={data['upstream_run_id']}\n")
        f.write(f"upstream_run_attempt={data['upstream_run_attempt']}\n")


def main_write() -> None:
    """Write authorization record."""
    if len(sys.argv) != 15:
        print(f"FATAL: expected 14 args, got {len(sys.argv) - 1}", file=sys.stderr)
        sys.exit(1)

    write_authorization_record(*sys.argv[1:15])
    print("AUTHORIZATION_WRITTEN=ok")


def main_verify() -> None:
    """Verify authorization record."""
    if len(sys.argv) != 2:
        print(f"FATAL: expected 1 arg, got {len(sys.argv) - 1}", file=sys.stderr)
        sys.exit(1)

    current_main = sys.argv[1]
    auth_dir = Path("artifacts/auth_extracted")
    data = verify_authorization_record(auth_dir, current_main)
    emit_outputs(data)
    print(f"AUTHORIZATION_VALID=PASS status={data['authorization_status']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        main_write()
    else:
        main_verify()
