#!/usr/bin/env python3
"""Strict record schema and immutable image contract validator."""
import json
import os
import re
import sys
from pathlib import Path

CANONICAL_REGISTRY = "harbor-pve1.spbnix.local"
CANONICAL_PROJECT = "k9b"
IMAGE_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")

REQUIRED_FIELDS = frozenset((
    "schema_version", "image_class", "subject_sha", "runtime_gate",
    "backend_image_ref", "scheduler_image_ref", "frontend_image_ref",
    "scheduler_uses_backend_image", "full_verify_remains_authoritative",
    "ready_for_image_publication", "ready_for_production_deployment",
    "ready_for_live_acceptance",
))

APPROVED_REPOS = {
    "backend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "scheduler": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-backend",
    "frontend": f"{CANONICAL_REGISTRY}/{CANONICAL_PROJECT}/k9b-frontend",
}


def strict_parse(content: str, expected_sha: str) -> tuple[dict[str, object], list[str]]:
    """Parse JSON with strict validation. Returns (data, errors)."""
    errors: list[str] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {}, [f"invalid JSON: {e}"]

    if not isinstance(data, dict):
        return {}, ["root must be object"]

    unknown = set(data.keys()) - REQUIRED_FIELDS
    if unknown:
        errors.append(f"unknown fields: {', '.join(sorted(unknown))}")

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"missing required fields: {', '.join(sorted(missing))}")

    for field, expected_type in [
        ("image_class", str), ("subject_sha", str), ("runtime_gate", str),
        ("scheduler_uses_backend_image", bool), ("full_verify_remains_authoritative", bool),
    ]:
        val = data.get(field)
        if not isinstance(val, expected_type):
            errors.append(f"{field} must be {expected_type.__name__}")

    for field in ("ready_for_image_publication", "ready_for_production_deployment",
                  "ready_for_live_acceptance"):
        if not isinstance(data.get(field), bool):
            errors.append(f"{field} must be bool")

    if data.get("image_class") != "experimental-lab":
        errors.append("image_class must be experimental-lab")
    if data.get("runtime_gate") != "pass":
        errors.append("runtime_gate must be pass")
    if data.get("scheduler_uses_backend_image") is not True:
        errors.append("scheduler_uses_backend_image must be true")
    if data.get("full_verify_remains_authoritative") is not True:
        errors.append("full_verify_remains_authoritative must be true")

    for field in ("ready_for_image_publication", "ready_for_production_deployment",
                  "ready_for_live_acceptance"):
        if data.get(field) is not False:
            errors.append(f"{field} must be false")

    if data.get("subject_sha") != expected_sha:
        errors.append(f"subject_sha mismatch: expected {expected_sha}")

    for label, repo in APPROVED_REPOS.items():
        ref = data.get(f"{label}_image_ref", "")
        if not isinstance(ref, str):
            errors.append(f"{label}_image_ref must be string")
            continue
        if not IMAGE_PATTERN.match(ref):
            errors.append(f"malformed {label}_image_ref: {ref}")
        else:
            repo_part = ref.split("@")[0]
            if repo_part != repo:
                errors.append(f"wrong repository for {label}: expected {repo}")

    if data.get("scheduler_image_ref") != data.get("backend_image_ref"):
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

    data, errors = strict_parse(paths[0].read_text(), expected_sha)
    if errors:
        for e in errors:
            print(f"FATAL: {e}")
        sys.exit(1)

    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a", encoding="utf-8") as f:
        f.write(f"backend_image_ref={data['backend_image_ref']}\n")
        f.write(f"scheduler_image_ref={data['scheduler_image_ref']}\n")
        f.write(f"frontend_image_ref={data['frontend_image_ref']}\n")

    print("SCHEMA_AND_IMAGE_CONTRACT=PASS")


if __name__ == "__main__":
    main()
