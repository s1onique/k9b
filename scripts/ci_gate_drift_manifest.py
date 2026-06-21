"""Manifest loading and validation for CI gate drift verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict, cast


class GateConfig(TypedDict, total=False):
    """Type for gate configuration in manifest."""
    ci_equivalent: list[str] | dict[str, list[str]]
    required_command_fragments: list[str]
    reason: str
    shard_required: bool
    shard_union_required: bool


class AllowlistEntry(TypedDict):
    """Type for allowlist entry in manifest."""
    gate: str
    workflow: str
    reason: str


class ManifestMetadata(TypedDict):
    """Type for manifest metadata."""
    version: str
    description: str | None


class Manifest(TypedDict):
    """Type for the complete CI gate mapping manifest."""
    _metadata: ManifestMetadata
    required_gates: dict[str, GateConfig]
    workflows_to_check: list[str]
    allowlist: list[AllowlistEntry]


def load_manifest(path: Path) -> Manifest:
    """Load the CI gate mapping manifest."""
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)
        return cast(Manifest, raw)  # Cast JSON dict to Manifest type


def validate_manifest(manifest: Manifest) -> list[str]:
    """Validate manifest structure. Returns list of error messages."""
    errors = []

    if "_metadata" not in manifest:
        errors.append("Manifest missing '_metadata' section")
    elif "version" not in manifest["_metadata"]:
        errors.append("Manifest missing '_metadata.version'")

    if "required_gates" not in manifest:
        errors.append("Manifest missing 'required_gates' section")
    elif not isinstance(manifest["required_gates"], dict):
        errors.append("'required_gates' must be a dictionary")
    else:
        # workflows_to_check: reserved for future per-workflow validation
        _: list[str] = manifest.get("workflows_to_check", [])
        for gate_id, gate_config in manifest["required_gates"].items():
            ci_equiv = gate_config.get("ci_equivalent")
            if ci_equiv is None:
                errors.append(f"Gate '{gate_id}' missing 'ci_equivalent'")
            elif isinstance(ci_equiv, dict):
                # Per-workflow format: harbor.yml is the only canonical push workflow
                if ".github/workflows/harbor.yml" not in ci_equiv:
                    errors.append(f"Gate '{gate_id}' missing ci_equivalent for canonical workflow '.github/workflows/harbor.yml'")
            elif isinstance(ci_equiv, list):
                if not ci_equiv:
                    errors.append(f"Gate '{gate_id}.ci_equivalent' is empty list")

            if "required_command_fragments" not in gate_config:
                errors.append(f"Gate '{gate_id}' missing 'required_command_fragments'")

            if "reason" not in gate_config:
                errors.append(f"Gate '{gate_id}' missing 'reason'")

    if "workflows_to_check" not in manifest:
        errors.append("Manifest missing 'workflows_to_check' section")

    if "allowlist" in manifest:
        for i, entry in enumerate(manifest["allowlist"]):
            if "gate" not in entry:
                errors.append(f"Allowlist entry {i} missing 'gate'")
            if "workflow" not in entry:
                errors.append(f"Allowlist entry {i} missing 'workflow'")
            if "reason" not in entry:
                errors.append(f"Allowlist entry {i} missing 'reason'")
            elif len(entry["reason"].strip()) < 10:
                errors.append(f"Allowlist entry {i} has insufficient reason (< 10 chars)")

    return errors
