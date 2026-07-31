#!/usr/bin/env python3
"""Artifact authority: upstream identity, exact artifact selection, strict record parsing."""
from __future__ import annotations

import argparse
import hashlib
import json
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


class ArtifactError(Exception):
    """Raised on validation failure."""


def parse_artifact_envelope_strict(content: str) -> list[dict[str, Any]]:
    """Parse GitHub REST artifact list response with strict duplicate-key rejection."""
    seen_keys: dict[str, None] = {}

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen_keys:
                raise ArtifactError(f"Duplicate key in envelope: {key}")
            seen_keys[key] = None
            result[key] = value
        return result

    try:
        data = json.loads(content, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as e:
        raise ArtifactError(f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise ArtifactError("Artifact response must be object")

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
    expected_run_attempt: int,
    expected_subject_sha: str,
    expected_repository_id: str,
) -> dict[str, Any]:
    """Select exactly one artifact and validate documented metadata fields."""
    matching = [a for a in artifacts_data if a.get("name") == "experimental-lab-record"]
    if len(matching) != 1:
        raise ArtifactError(f"Expected exactly 1 artifact, found {len(matching)}")

    artifact = matching[0]
    if artifact.get("expired", False):
        raise ArtifactError("Artifact is expired")

    wr = artifact.get("workflow_run", {})
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


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_strict_record(content: str, expected_sha: str) -> dict[str, Any]:
    """Parse JSON with strict validation including duplicate-key rejection."""
    seen_keys: dict[str, None] = {}

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen_keys:
                raise ArtifactError(f"Duplicate key: {key}")
            seen_keys[key] = None
            result[key] = value
        return result

    try:
        data = json.loads(content, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as e:
        raise ArtifactError(f"Invalid JSON: {e}")
    except TypeError as e:
        raise ArtifactError(f"JSON structure error: {e}")

    if not isinstance(data, dict):
        raise ArtifactError("Root must be object")

    unknown = set(data.keys()) - REQUIRED_RECORD_FIELDS
    if unknown:
        raise ArtifactError(f"Unknown fields: {', '.join(sorted(unknown))}")

    missing = REQUIRED_RECORD_FIELDS - set(data.keys())
    if missing:
        raise ArtifactError(f"Missing fields: {', '.join(sorted(missing))}")

    type_checks: list[tuple[str, type]] = [
        ("image_class", str), ("subject_sha", str), ("runtime_gate", str),
        ("scheduler_uses_backend_image", bool), ("full_verify_remains_authoritative", bool),
        ("ready_for_image_publication", bool), ("ready_for_production_deployment", bool),
        ("ready_for_live_acceptance", bool),
        ("upstream_run_id", str), ("upstream_run_attempt", str),
    ]
    for field_name, expected_type in type_checks:
        val = data.get(field_name)
        if not isinstance(val, expected_type):
            raise ArtifactError(f"{field_name} must be {expected_type.__name__}")

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


def validate(
    metadata_json: Path,
    expected_run_id: int,
    expected_run_attempt: int,
    expected_subject_sha: str,
    expected_repository_id: str,
    output: Path,
) -> dict[str, Any]:
    """Validate artifact metadata and record."""
    content = metadata_json.read_text()
    artifacts_data = parse_artifact_envelope_strict(content)

    artifact = validate_artifact_metadata(
        artifacts_data,
        expected_run_id,
        expected_run_attempt,
        expected_subject_sha,
        expected_repository_id,
    )

    record_path = Path("artifacts/record_extracted")
    exact_record = record_path / "experimental-lab-record.json"
    if not exact_record.exists():
        raise ArtifactError("Missing experimental-lab-record.json")
    if not exact_record.is_file():
        raise ArtifactError("experimental-lab-record.json is not a file")

    record_data = parse_strict_record(exact_record.read_text(), expected_subject_sha)

    if record_data.get("upstream_run_id") != str(expected_run_id):
        raise ArtifactError(
            f"Record run ID mismatch: expected {expected_run_id}, "
            f"got {record_data.get('upstream_run_id')}"
        )
    if record_data.get("upstream_run_attempt") != str(expected_run_attempt):
        raise ArtifactError(
            f"Record run attempt mismatch: expected {expected_run_attempt}, "
            f"got {record_data.get('upstream_run_attempt')}"
        )

    record_sha = compute_sha256(exact_record)

    result = {
        "artifact_id": str(artifact["id"]),
        "artifact_name": artifact["name"],
        "artifact_metadata_digest": artifact["digest"],
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

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Artifact authority CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate artifact and record")
    validate_parser.add_argument("--metadata-json", type=Path, required=True)
    validate_parser.add_argument("--expected-run-id", type=int, required=True)
    validate_parser.add_argument("--expected-run-attempt", type=int, required=True)
    validate_parser.add_argument("--expected-subject-sha", required=True)
    validate_parser.add_argument("--expected-repository-id", required=True)
    validate_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "validate":
        result = validate(
            Path(args.metadata_json),
            args.expected_run_id,
            args.expected_run_attempt,
            args.expected_subject_sha,
            args.expected_repository_id,
            Path(args.output),
        )
        print(f"ARTIFACT_VALIDATION=PASS artifact_id={result['artifact_id']}")


if __name__ == "__main__":
    main()
