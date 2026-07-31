#!/usr/bin/env python3
"""Artifact authority: upstream identity, exact artifact selection, strict record parsing."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

IMAGE_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
CANONICAL_REGISTRY = "harbor-pve1.spbnix.local"
CANONICAL_PROJECT = "k9b"

REQUIRED_RECORD_FIELDS = frozenset((
    "schema_version", "image_class", "subject_sha", "runtime_gate",
    "backend_image_ref", "scheduler_image_ref", "frontend_image_ref",
    "scheduler_uses_backend_image", "full_verify_remains_authoritative",
    "ready_for_image_publication", "ready_for_production_deployment",
    "ready_for_live_acceptance",
))

IMAGE_REPOSITORIES: dict[str, str] = {
    "backend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "scheduler": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "frontend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-frontend",
}


class ArtifactError(Exception):
    """Raised on validation failure."""


def validate_artifacts_json(data: list[dict[str, Any]], run_id: int, run_sha: str) -> dict[str, Any]:
    """Select exactly one artifact by exact name and validate metadata."""
    matching = [a for a in data if a.get("name") == "experimental-lab-record"]
    if len(matching) != 1:
        raise ArtifactError(f"Expected exactly 1 artifact, found {len(matching)}")
    artifact = matching[0]
    if artifact.get("expired", False):
        raise ArtifactError("Artifact is expired")
    wr = artifact.get("workflow_run", {})
    if wr.get("id") != run_id:
        raise ArtifactError(f"Run ID mismatch: expected {run_id}, got {wr.get('id')}")
    if wr.get("head_sha") != run_sha:
        raise ArtifactError(f"Run SHA mismatch: expected {run_sha}, got {wr.get('head_sha')}")
    if wr.get("repository", {}).get("id") != os.environ.get("GITHUB_REPOSITORY_ID", ""):
        raise ArtifactError("Repository ID mismatch")
    digest = artifact.get("digest", "")
    if not digest.startswith("sha256:"):
        raise ArtifactError(f"Missing digest: {digest}")
    return artifact


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_strict_record(content: str, expected_sha: str) -> dict[str, Any]:
    """Parse JSON with strict validation."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ArtifactError(f"Invalid JSON: {e}")

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
    ]
    for field, expected_type in type_checks:
        val = data.get(field)
        if not isinstance(val, expected_type):
            raise ArtifactError(f"{field} must be {expected_type.__name__}")

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


def validate_upstream_and_record(upstream_run_id: int, upstream_run_sha: str) -> dict[str, Any]:
    """Validate upstream artifact and parse record."""
    if not IMAGE_PATTERN:
        raise ArtifactError("Invalid environment")

    artifacts_path = Path("artifacts/record_extracted")
    paths = list(artifacts_path.glob("*.json"))

    if len(paths) == 0:
        raise ArtifactError("No JSON in artifact")
    if len(paths) > 1:
        raise ArtifactError("Multiple JSON files in artifact")

    data = parse_strict_record(paths[0].read_text(), upstream_run_sha)
    return data


def main() -> None:
    if len(sys.argv) != 4:
        print(f"FATAL: expected 3 args, got {len(sys.argv) - 1}", file=sys.stderr)
        sys.exit(1)

    upstream_run_id = int(sys.argv[1])
    upstream_run_sha = sys.argv[2]
    artifact_digest = sys.argv[3]

    data = validate_upstream_and_record(upstream_run_id, upstream_run_sha)
    record_sha = compute_sha256(list(Path("artifacts/record_extracted").glob("*.json"))[0])

    output_file = Path("artifacts/artifact_result.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps({
        "backend_image_ref": data["backend_image_ref"],
        "scheduler_image_ref": data["scheduler_image_ref"],
        "frontend_image_ref": data["frontend_image_ref"],
        "record_sha256": record_sha,
        "artifact_digest": artifact_digest,
        "subject_sha": data["subject_sha"],
        "upstream_run_id": upstream_run_id,
        "upstream_run_sha": upstream_run_sha,
    }, indent=2) + "\n")

    print(f"ARTIFACT_VALIDATION=PASS record_sha={record_sha[:16]}...")


if __name__ == "__main__":
    main()
