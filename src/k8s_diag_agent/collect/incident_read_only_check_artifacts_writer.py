"""Pure helper module for writing read-only check result artifacts.

This module provides write logic for persisting fake runner results
as bounded JSON artifacts.

Design constraints:
- Bounded file IO only in explicit write functions
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic JSON output
- Explicit safety metadata

Artifact naming convention:
- {run_id}-read-only-check-results.json

Path safety:
- run_id values are validated against strict character constraints
- Unsafe run_ids are rejected without path construction
- Only exact expected filenames are written (no glob/recursive patterns)
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Import safety helpers from loader module (shared)
from .incident_read_only_check_artifacts_loader import (
    _FORBIDDEN_ACTION_FIELDS,
    _truncate_evidence,
    _truncate_string,
    is_safe_run_id,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "write_read_only_check_result_artifact",
    "ARTIFACT_SCHEMA_VERSION",
]


# =============================================================================
# Constants
# =============================================================================

# Artifact schema version
ARTIFACT_SCHEMA_VERSION = "1.0"

# Bounds for writing
DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS = 500
DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS = 2000


# =============================================================================
# Bounded Write Helpers
# =============================================================================


def _strip_action_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove action-control fields from a dict.

    Args:
        data: Input dict that may contain action fields

    Returns:
        Filtered dict without action-control fields
    """
    return {k: v for k, v in data.items() if k not in _FORBIDDEN_ACTION_FIELDS}


def _bound_runner_result_for_write(runner_result: Mapping[str, object]) -> dict[str, object]:
    """Bound a runner result for safe artifact writing.

    Applies:
    - Action-field stripping
    - Result truncation
    - Summary truncation
    - Evidence truncation

    Args:
        runner_result: Raw runner result from run_read_only_checks()

    Returns:
        Bounded runner result suitable for artifact storage
    """
    bounded: dict[str, object] = {
        "checks_requested": runner_result.get("checks_requested", 0),
        "checks_run": runner_result.get("checks_run", 0),
        "checks_skipped": runner_result.get("checks_skipped", 0),
        "checks_rejected": runner_result.get("checks_rejected", 0),
    }

    # Bound results
    results: list[dict[str, Any]] = []
    raw_results = runner_result.get("results", [])
    if isinstance(raw_results, list):
        for item in raw_results[:20]:  # Limit to 20 results
            if not isinstance(item, dict):
                continue

            safe_item = _strip_action_fields(dict(item))

            # Truncate summary
            summary = safe_item.get("summary")
            if summary is not None:
                safe_item["summary"] = _truncate_string(summary, DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS)

            # Truncate evidence
            evidence = safe_item.get("evidence")
            if isinstance(evidence, dict):
                safe_item["evidence"] = _truncate_evidence(evidence, DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS)

            results.append(safe_item)

    bounded["results"] = results

    # Bound skipped checks
    skipped: list[dict[str, Any]] = []
    raw_skipped = runner_result.get("skipped_checks", [])
    if isinstance(raw_skipped, list):
        for item in raw_skipped[:10]:  # Limit to 10
            if isinstance(item, dict):
                skipped.append(_strip_action_fields(dict(item)))

    bounded["skipped_checks"] = skipped

    # Bound rejected checks
    rejected: list[dict[str, Any]] = []
    raw_rejected = runner_result.get("rejected_checks", [])
    if isinstance(raw_rejected, list):
        for item in raw_rejected[:10]:  # Limit to 10
            if isinstance(item, dict):
                rejected.append(_strip_action_fields(dict(item)))

    bounded["rejected_checks"] = rejected

    return bounded


# =============================================================================
# Public API
# =============================================================================


def write_read_only_check_result_artifact(
    *,
    external_analysis_dir: Path,
    run_id: str,
    incident_id: str,
    runner_result: Mapping[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    """Write a read-only check result artifact to disk.

    This function persists fake runner output as a bounded JSON artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: Unique identifier for this run (must be safe)
        incident_id: The incident ID this artifact belongs to
        runner_result: The runner result from run_read_only_checks()
        now: Optional datetime for deterministic timestamps

    Returns:
        Dict with artifact metadata including path and status

    Raises:
        ValueError: If run_id is unsafe

    Safety:
        - Validates run_id against strict character constraints
        - Does not write outside external_analysis_dir
        - Does not create parent directories outside artifact root
        - Does not follow symlinks outside artifact directory
    """
    # Safety check: reject unsafe run_ids
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Construct artifact path (from loader module)
    from .incident_read_only_check_artifacts_loader import _artifact_path_for_run

    artifact_path = _artifact_path_for_run(external_analysis_dir, run_id)
    if artifact_path is None:
        raise ValueError(f"Could not construct artifact path for run_id: {run_id!r}")

    # Ensure parent directory exists
    external_analysis_dir.mkdir(parents=True, exist_ok=True)

    # Build artifact envelope
    artifact: dict[str, object] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "read-only-check-results",
        "run_id": run_id,
        "incident_id": incident_id,
        "generated_at": resolved_now.isoformat(),
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": [
            "execute",
            "promote",
            "apply",
            "remediate",
            "delete",
            "mutate_cluster",
            "mutate",
            "scale",
            "restart",
            "rollout",
        ],
        "source": "fake-read-only-check-runner",
        "bounded": True,
        "runner_result": _bound_runner_result_for_write(runner_result),
        "safety_metadata": {
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": [
                "execute",
                "promote",
                "apply",
                "remediate",
                "delete",
                "mutate_cluster",
            ],
            "no_kubernetes_client": True,
            "no_shell": True,
            "no_subprocess": True,
            "no_kubectl": True,
            "no_mutation": True,
            "fake_runner": True,
            "bounded": True,
        },
    }

    # Write artifact as deterministic JSON
    artifact_json = json.dumps(artifact, default=str, indent=2)
    artifact_path.write_text(artifact_json, encoding="utf-8")

    return {
        "artifact_path": str(artifact_path),
        "run_id": run_id,
        "incident_id": incident_id,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "written": True,
    }
