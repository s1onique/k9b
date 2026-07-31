#!/usr/bin/env python3
"""Authorization authority: record construction, atomic writes, checksum verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path


@dataclass
class AuthorizationRecord:
    """Typed authorization record."""
    schema_version: str = ""
    authorization_status: str = ""
    subject_sha: str = ""
    upstream_run_id: str = ""
    current_main_sha: str = ""
    backend_image_ref: str = ""
    scheduler_image_ref: str = ""
    frontend_image_ref: str = ""
    record_sha256: str = ""
    artifact_id: str = ""
    artifact_name: str = ""
    artifact_metadata_digest: str = ""
    bridge_sha: str = ""
    bridge_run_id: str = ""
    bridge_run_attempt: str = ""
    authorization_time: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authorization_status": self.authorization_status,
            "subject_sha": self.subject_sha,
            "upstream_run_id": self.upstream_run_id,
            "current_main_sha": self.current_main_sha,
            "backend_image_ref": self.backend_image_ref,
            "scheduler_image_ref": self.scheduler_image_ref,
            "frontend_image_ref": self.frontend_image_ref,
            "record_sha256": self.record_sha256,
            "artifact_id": self.artifact_id,
            "artifact_name": self.artifact_name,
            "artifact_metadata_digest": self.artifact_metadata_digest,
            "bridge_sha": self.bridge_sha,
            "bridge_run_id": self.bridge_run_id,
            "bridge_run_attempt": self.bridge_run_attempt,
            "authorization_time": self.authorization_time,
        }

    REQUIRED_FIELDS: tuple[str, ...] = (
        "schema_version", "authorization_status", "subject_sha", "upstream_run_id",
        "current_main_sha", "backend_image_ref", "scheduler_image_ref",
        "frontend_image_ref", "record_sha256", "artifact_id", "artifact_name",
        "artifact_metadata_digest", "bridge_sha", "bridge_run_id",
        "bridge_run_attempt", "authorization_time",
    )


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    """Atomically write content to path using temp file + fsync + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
        temp_path = Path(f.name)
    try:
        os.replace(temp_path, path)
        # Sync parent directory
        parent_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def parse_strict_auth(content: str) -> dict[str, str]:
    """Parse authorization JSON with duplicate-key rejection and strict schema."""
    seen_keys: dict[str, None] = {}

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in pairs:
            if key in seen_keys:
                raise ValueError(f"Duplicate key: {key}")
            seen_keys[key] = None
            if not isinstance(value, str):
                raise ValueError(f"{key} must be string")
            result[key] = value
        return result

    data = json.loads(content, object_pairs_hook=reject_duplicates)
    if not isinstance(data, dict):
        raise ValueError("Authorization record must be object")

    unknown = set(data.keys()) - set(AuthorizationRecord.REQUIRED_FIELDS)
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")

    missing = set(AuthorizationRecord.REQUIRED_FIELDS) - set(data.keys())
    if missing:
        raise ValueError(f"Missing fields: {', '.join(sorted(missing))}")

    return data


def write_authorization_record(
    artifact_result_path: Path,
    current_main_sha: str,
    bridge_sha: str,
    bridge_run_id: str,
    bridge_run_attempt: str,
    authorization_status: str,
    output_dir: Path,
    github_output: Path,
) -> None:
    """Write authorization record and checksum sidecar atomically."""
    result = json.loads(artifact_result_path.read_text())
    digest = result.get("artifact_metadata_digest", "")
    if not digest:
        raise ValueError("Missing artifact_metadata_digest in artifact result")

    record = AuthorizationRecord(
        schema_version="1.0",
        authorization_status=authorization_status,
        subject_sha=result["subject_sha"],
        upstream_run_id=result["upstream_run_id"],
        current_main_sha=current_main_sha,
        backend_image_ref=result["backend_image_ref"],
        scheduler_image_ref=result["scheduler_image_ref"],
        frontend_image_ref=result["frontend_image_ref"],
        record_sha256=result["record_sha256"],
        artifact_id=result["artifact_id"],
        artifact_name=result["artifact_name"],
        artifact_metadata_digest=digest,
        bridge_sha=bridge_sha,
        bridge_run_id=bridge_run_id,
        bridge_run_attempt=bridge_run_attempt,
        authorization_time=datetime.now(UTC).isoformat(),
    )

    json_content = json.dumps(record.to_dict(), indent=2) + "\n"
    json_path = output_dir / "experimental-lab-deploy-authorization.json"
    atomic_write(json_path, json_content)

    sha_path = output_dir / "experimental-lab-deploy-authorization.json.sha256"
    sha_value = compute_sha256(json_path)
    atomic_write(sha_path, sha_value + "\n")

    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"auth_artifact_path={json_path}\n")
        f.write(f"auth_artifact_sha256={sha_value}\n")

    print(f"AUTHORIZATION_WRITTEN={json_path}")


def verify_authorization_record(
    auth_dir: Path,
    current_main_sha: str,
    github_output: Path,
) -> AuthorizationRecord:
    """Verify authorization record and checksum sidecar."""
    json_path = auth_dir / "experimental-lab-deploy-authorization.json"
    sha_path = auth_dir / "experimental-lab-deploy-authorization.json.sha256"

    if not json_path.exists():
        raise ValueError(f"No authorization JSON: {json_path}")
    if not sha_path.exists():
        raise ValueError(f"No checksum sidecar: {sha_path}")

    expected_sha = sha_path.read_text().strip()
    actual_sha = compute_sha256(json_path)
    if expected_sha != actual_sha:
        raise ValueError(f"Checksum mismatch: expected {expected_sha}, got {actual_sha}")

    content = json_path.read_text()
    data = parse_strict_auth(content)

    record = AuthorizationRecord(
        schema_version=data["schema_version"],
        authorization_status=data["authorization_status"],
        subject_sha=data["subject_sha"],
        upstream_run_id=data["upstream_run_id"],
        current_main_sha=data["current_main_sha"],
        backend_image_ref=data["backend_image_ref"],
        scheduler_image_ref=data["scheduler_image_ref"],
        frontend_image_ref=data["frontend_image_ref"],
        record_sha256=data["record_sha256"],
        artifact_id=data["artifact_id"],
        artifact_name=data["artifact_name"],
        artifact_metadata_digest=data["artifact_metadata_digest"],
        bridge_sha=data["bridge_sha"],
        bridge_run_id=data["bridge_run_id"],
        bridge_run_attempt=data["bridge_run_attempt"],
        authorization_time=data["authorization_time"],
    )

    if record.authorization_status != "authorized":
        raise ValueError(f"Authorization status not authorized: {record.authorization_status}")

    if record.current_main_sha != current_main_sha:
        raise ValueError(
            f"Main SHA mismatch: expected {current_main_sha}, "
            f"got {record.current_main_sha}"
        )

    if record.subject_sha != current_main_sha:
        raise ValueError(
            f"Subject SHA {record.subject_sha} != current main {current_main_sha}"
        )

    if not record.artifact_metadata_digest:
        raise ValueError("Empty artifact_metadata_digest")

    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"subject_sha={record.subject_sha}\n")
        f.write(f"backend_image_ref={record.backend_image_ref}\n")
        f.write(f"scheduler_image_ref={record.scheduler_image_ref}\n")
        f.write(f"frontend_image_ref={record.frontend_image_ref}\n")
        f.write(f"artifact_metadata_digest={record.artifact_metadata_digest}\n")
        f.write(f"upstream_run_id={record.upstream_run_id}\n")

    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorization authority CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="Write authorization record")
    write_parser.add_argument("--artifact-result", type=Path, required=True)
    write_parser.add_argument("--current-main-sha", required=True)
    write_parser.add_argument("--bridge-sha", required=True)
    write_parser.add_argument("--bridge-run-id", required=True)
    write_parser.add_argument("--bridge-run-attempt", required=True)
    write_parser.add_argument("--authorization-status", required=True)
    write_parser.add_argument("--output-dir", type=Path, required=True)
    write_parser.add_argument("--github-output", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify", help="Verify authorization record")
    verify_parser.add_argument("--auth-dir", type=Path, required=True)
    verify_parser.add_argument("--current-main-sha", required=True)
    verify_parser.add_argument("--github-output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "write":
        write_authorization_record(
            Path(args.artifact_result),
            args.current_main_sha,
            args.bridge_sha,
            args.bridge_run_id,
            args.bridge_run_attempt,
            args.authorization_status,
            Path(args.output_dir),
            Path(args.github_output),
        )
    elif args.command == "verify":
        record = verify_authorization_record(
            Path(args.auth_dir),
            args.current_main_sha,
            Path(args.github_output),
        )
        print(f"AUTHORIZATION_VALID=PASS status={record.authorization_status}")


if __name__ == "__main__":
    main()
