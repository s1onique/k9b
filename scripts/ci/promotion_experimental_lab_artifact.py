#!/usr/bin/env python3
"""Artifact authority: upstream identity, exact artifact selection, strict record parsing."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

IMAGE_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

CANONICAL_REGISTRY = "harbor-pve1.spbnix.local"
CANONICAL_PROJECT = "k9b"

REQUIRED_RECORD_FIELDS = frozenset((
    "schema_version", "image_class", "subject_sha", "runtime_gate",
    "backend_image_ref", "scheduler_image_ref", "frontend_image_ref",
    "scheduler_uses_backend_image", "full_verify_remains_authoritative",
    "ready_for_image_publication", "ready_for_production_deployment",
    "ready_for_live_acceptance", "upstream_run_id", "upstream_run_attempt",
))

IMAGE_REPOSITORIES: dict[str, str] = {
    "backend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "scheduler": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "frontend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-frontend",
}

CANONICAL_ARTIFACT_NAME = "experimental-lab-record"
CANONICAL_RECORD_FILENAME = "experimental-lab-record.json"


class ArtifactError(Exception):
    """Raised on validation failure."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys within a single JSON object."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError(f"Duplicate key in JSON object: {key}")
        result[key] = value
    return result


def _strict_json_loads(content: str, *, context: str) -> dict[str, Any]:
    """Parse JSON with object-local strict duplicate-key rejection."""
    try:
        data = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as e:
        raise ArtifactError(f"Invalid JSON in {context}: {e}")

    if not isinstance(data, dict):
        raise ArtifactError(f"Root must be object in {context}")

    def check_numbers(obj: Any) -> None:
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                raise ArtifactError(f"NaN/Infinity not allowed in {context}")
        elif isinstance(obj, dict):
            for v in obj.values():
                check_numbers(v)
        elif isinstance(obj, list):
            for item in obj:
                check_numbers(item)

    check_numbers(data)
    return data


def _write_github_output(github_output: Path, values: dict[str, str]) -> None:
    """Append name=value pairs to the runner's GITHUB_OUTPUT file."""
    with github_output.open("a", encoding="utf-8", newline="\n") as stream:
        for name, value in values.items():
            if not name or not value:
                raise ArtifactError("GitHub output name and value must be nonempty")
            if "\n" in name or "\r" in name:
                raise ArtifactError("GitHub output name contains newline")
            if "\n" in value or "\r" in value:
                raise ArtifactError("GitHub output value contains newline")
            stream.write(f"{name}={value}\n")


def parse_artifact_envelope_strict(content: str) -> list[dict[str, Any]]:
    """Parse GitHub REST artifact list response with object-local duplicate-key rejection."""
    data = _strict_json_loads(content, context="artifact_metadata")

    if "total_count" not in data:
        raise ArtifactError("Missing total_count in artifact response")
    if not isinstance(data["total_count"], int):
        raise ArtifactError(f"total_count must be int, got {type(data['total_count']).__name__}")
    if isinstance(data["total_count"], bool):
        raise ArtifactError("total_count cannot be boolean")

    if "artifacts" not in data:
        raise ArtifactError("Missing artifacts in artifact response")
    artifacts = data["artifacts"]
    if not isinstance(artifacts, list):
        raise ArtifactError("artifacts must be array")

    for i, art in enumerate(artifacts):
        if not isinstance(art, dict):
            raise ArtifactError(f"Artifact[{i}] must be object")

    total = data["total_count"]
    if len(artifacts) != total:
        raise ArtifactError(f"total_count mismatch: {total} vs {len(artifacts)}")

    return artifacts


def validate_artifact_metadata(
    artifacts_data: list[dict[str, Any]],
    expected_run_id: int,
    expected_subject_sha: str,
    expected_repository_id: str,
) -> dict[str, Any]:
    """Select exactly one artifact and validate documented metadata fields."""
    matching = [a for a in artifacts_data if a.get("name") == CANONICAL_ARTIFACT_NAME]
    if len(matching) != 1:
        raise ArtifactError(f"Expected exactly 1 artifact named '{CANONICAL_ARTIFACT_NAME}', found {len(matching)}")

    artifact = matching[0]
    if artifact.get("expired", False):
        raise ArtifactError("Artifact is expired")

    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or artifact_id <= 0:
        raise ArtifactError(f"artifact_id must be positive integer, got {artifact_id}")

    wr = artifact.get("workflow_run", {})
    if not isinstance(wr, dict):
        raise ArtifactError("workflow_run must be object")

    if wr.get("id") != expected_run_id:
        raise ArtifactError(f"Run ID mismatch: expected {expected_run_id}, got {wr.get('id')}")
    if wr.get("head_sha") != expected_subject_sha:
        raise ArtifactError(f"Head SHA mismatch: expected {expected_subject_sha}, got {wr.get('head_sha')}")

    repo_id = str(wr.get("repository_id", ""))
    if repo_id != expected_repository_id:
        raise ArtifactError(f"Repository ID mismatch: expected {expected_repository_id}, got {repo_id}")

    head_repo_id = str(wr.get("head_repository_id", ""))
    if head_repo_id != expected_repository_id:
        raise ArtifactError(f"Head repository ID mismatch: expected {expected_repository_id}, got {head_repo_id}")

    head_branch = wr.get("head_branch", "")
    if head_branch != "main":
        raise ArtifactError(f"Head branch mismatch: expected main, got {head_branch}")

    digest = artifact.get("digest", "")
    if not digest:
        raise ArtifactError("Missing digest")
    if not DIGEST_PATTERN.match(digest):
        raise ArtifactError(f"Malformed digest: {digest}")

    return artifact


def select_metadata(
    metadata_json: Path,
    expected_run_id: int,
    expected_subject_sha: str,
    expected_repository_id: str,
    output: Path,
    github_output: Path,
) -> dict[str, Any]:
    """Validate artifact metadata only - no file access."""
    content = metadata_json.read_text()
    artifacts_data = parse_artifact_envelope_strict(content)

    artifact = validate_artifact_metadata(
        artifacts_data,
        expected_run_id,
        expected_subject_sha,
        expected_repository_id,
    )

    artifact_id_str = str(artifact["id"])
    artifact_name = artifact["name"]
    artifact_digest = artifact["digest"]

    result = {
        "artifact_id": artifact_id_str,
        "artifact_name": artifact_name,
        "artifact_metadata_digest": artifact_digest,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")

    _write_github_output(github_output, result)

    return result


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_strict_record(content: str, expected_sha: str) -> dict[str, Any]:
    """Parse JSON with object-local strict duplicate-key rejection."""
    data = _strict_json_loads(content, context="experimental_record")

    unknown = set(data.keys()) - REQUIRED_RECORD_FIELDS
    if unknown:
        raise ArtifactError(f"Unknown fields: {', '.join(sorted(unknown))}")

    missing = REQUIRED_RECORD_FIELDS - set(data.keys())
    if missing:
        raise ArtifactError(f"Missing fields: {', '.join(sorted(missing))}")

    type_checks: list[tuple[str, type]] = [
        ("schema_version", str),
        ("image_class", str),
        ("subject_sha", str),
        ("runtime_gate", str),
        ("scheduler_uses_backend_image", bool),
        ("full_verify_remains_authoritative", bool),
        ("ready_for_image_publication", bool),
        ("ready_for_production_deployment", bool),
        ("ready_for_live_acceptance", bool),
        ("upstream_run_id", int),
        ("upstream_run_attempt", int),
    ]
    for field_name, expected_type in type_checks:
        val = data.get(field_name)
        if not isinstance(val, expected_type):
            raise ArtifactError(f"{field_name} must be {expected_type.__name__}, got {type(val).__name__}")

    if data.get("image_class") != "experimental-lab":
        raise ArtifactError("image_class must be experimental-lab")
    if data.get("runtime_gate") != "pass":
        raise ArtifactError("runtime_gate must be pass")
    if data.get("scheduler_uses_backend_image") is not True:
        raise ArtifactError("scheduler_uses_backend_image must be true")
    if data.get("full_verify_remains_authoritative") is not True:
        raise ArtifactError("full_verify_remains_authoritative must be true")
    if data.get("ready_for_image_publication") is not False:
        raise ArtifactError("ready_for_image_publication must be false")
    if data.get("ready_for_production_deployment") is not False:
        raise ArtifactError("ready_for_production_deployment must be false")
    if data.get("ready_for_live_acceptance") is not False:
        raise ArtifactError("ready_for_live_acceptance must be false")

    run_id = data.get("upstream_run_id", 0)
    if not isinstance(run_id, int) or run_id <= 0:
        raise ArtifactError(f"upstream_run_id must be positive integer, got {run_id}")

    run_attempt = data.get("upstream_run_attempt", 0)
    if not isinstance(run_attempt, int) or run_attempt <= 0:
        raise ArtifactError(f"upstream_run_attempt must be positive integer, got {run_attempt}")

    if data.get("subject_sha") != expected_sha:
        raise ArtifactError(f"subject_sha mismatch: expected {expected_sha}")

    for label, repo in IMAGE_REPOSITORIES.items():
        ref = data.get(f"{label}_image_ref", "")
        if not isinstance(ref, str):
            raise ArtifactError(f"{label}_image_ref must be string")
        if not IMAGE_PATTERN.match(ref):
            raise ArtifactError(f"Malformed {label}_image_ref: {ref}")
        repo_part = ref.split("@")[0]
        if repo_part != repo:
            raise ArtifactError(f"Wrong repository for {label}: expected {repo}")

    if data.get("scheduler_image_ref") != data.get("backend_image_ref"):
        raise ArtifactError("scheduler_image_ref != backend_image_ref")

    return data


def validate_record(
    record_path: Path,
    expected_run_id: int,
    expected_run_attempt: int,
    expected_subject_sha: str,
    artifact_id: str,
    artifact_metadata_digest: str,
    output: Path,
    github_output: Path,
) -> dict[str, Any]:
    """Validate downloaded record file - no network access."""
    if not record_path.exists():
        raise ArtifactError(f"Missing {CANONICAL_RECORD_FILENAME}")
    if not record_path.is_file():
        raise ArtifactError(f"{CANONICAL_RECORD_FILENAME} is not a regular file")
    if record_path.is_symlink():
        raise ArtifactError(f"{CANONICAL_RECORD_FILENAME} is a symlink")

    parent = record_path.parent
    if parent.name != "record_extracted":
        raise ArtifactError("Record must be in record_extracted directory")
    if record_path.name != CANONICAL_RECORD_FILENAME:
        raise ArtifactError(f"Record filename must be {CANONICAL_RECORD_FILENAME}")

    other_files = [p for p in parent.iterdir() if p != record_path and p.name != ".gitkeep"]
    if other_files:
        raise ArtifactError(f"Unexpected files in artifact: {[str(p) for p in other_files]}")

    record_data = parse_strict_record(record_path.read_text(), expected_subject_sha)

    if record_data.get("upstream_run_id") != expected_run_id:
        raise ArtifactError(
            f"Record run ID mismatch: expected {expected_run_id}, "
            f"got {record_data.get('upstream_run_id')}"
        )
    if record_data.get("upstream_run_attempt") != expected_run_attempt:
        raise ArtifactError(
            f"Record run attempt mismatch: expected {expected_run_attempt}, "
            f"got {record_data.get('upstream_run_attempt')}"
        )

    record_sha = compute_sha256(record_path)

    result = {
        "artifact_id": artifact_id,
        "artifact_metadata_digest": artifact_metadata_digest,
        "backend_image_ref": record_data["backend_image_ref"],
        "scheduler_image_ref": record_data["scheduler_image_ref"],
        "frontend_image_ref": record_data["frontend_image_ref"],
        "record_sha256": record_sha,
        "subject_sha": record_data["subject_sha"],
        "upstream_run_id": str(expected_run_id),
        "upstream_run_attempt": str(expected_run_attempt),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")

    _write_github_output(github_output, result)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Artifact authority CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    select_parser = subparsers.add_parser("select-metadata", help="Validate artifact metadata only")
    select_parser.add_argument("--metadata-json", type=Path, required=True)
    select_parser.add_argument("--expected-run-id", type=int, required=True)
    select_parser.add_argument("--expected-subject-sha", required=True)
    select_parser.add_argument("--expected-repository-id", required=True)
    select_parser.add_argument("--output", type=Path, required=True)
    select_parser.add_argument("--github-output", type=Path, required=True)

    record_parser = subparsers.add_parser("validate-record", help="Validate downloaded record")
    record_parser.add_argument("--record-path", type=Path, required=True)
    record_parser.add_argument("--expected-run-id", type=int, required=True)
    record_parser.add_argument("--expected-run-attempt", type=int, required=True)
    record_parser.add_argument("--expected-subject-sha", required=True)
    record_parser.add_argument("--artifact-id", required=True)
    record_parser.add_argument("--artifact-metadata-digest", required=True)
    record_parser.add_argument("--output", type=Path, required=True)
    record_parser.add_argument("--github-output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "select-metadata":
        result = select_metadata(
            Path(args.metadata_json),
            args.expected_run_id,
            args.expected_subject_sha,
            args.expected_repository_id,
            Path(args.output),
            Path(args.github_output),
        )
        print(f"METADATA_SELECTION=PASS artifact_id={result['artifact_id']}")

    elif args.command == "validate-record":
        result = validate_record(
            Path(args.record_path),
            args.expected_run_id,
            args.expected_run_attempt,
            args.expected_subject_sha,
            args.artifact_id,
            args.artifact_metadata_digest,
            Path(args.output),
            Path(args.github_output),
        )
        print(f"RECORD_VALIDATION=PASS artifact_id={result['artifact_id']}")


if __name__ == "__main__":
    main()
