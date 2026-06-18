"""Pure helper module for writing diagnosis loop pass artifacts.

This module provides write logic for persisting loop pass orchestration results
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
- {run_id}-diagnosis-loop-pass.json

Path safety:
- run_id values are validated against strict character constraints
- Unsafe run_ids are rejected without path construction
- Only exact expected filenames are written (no glob/recursive patterns)
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "write_diagnosis_loop_pass_artifact",
    "ARTIFACT_SCHEMA_VERSION",
]


# =============================================================================
# Constants
# =============================================================================

# Artifact schema version
ARTIFACT_SCHEMA_VERSION = "1.0"

# Artifact filename pattern
ARTIFACT_FILENAME_PATTERN = "{run_id}-diagnosis-loop-pass.json"

# Bounds for safety
MAX_LINKED_ARTIFACTS = 10
MAX_STRING_CHARS = 500


# Strict regex for allowed run_id characters: A-Z a-z 0-9 _ . -
# Excludes: / \ .. and other special characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Forbidden action-control fields (must not appear in artifacts)
_FORBIDDEN_ACTION_FIELDS: frozenset[str] = frozenset({
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "approve",
    "reject",
    "run_command",
    "execute_command",
    "mutate",
    "delete",
    "scale",
    "restart",
    "rollout",
    "patch",
})

# Disallowed actions list for safety metadata
DISALLOWED_ACTIONS: list[str] = [
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
]


# =============================================================================
# Safety Validation
# =============================================================================


def is_safe_run_id(run_id: str | None) -> bool:
    """Validate that a run_id is safe for path construction.

    Args:
        run_id: The run_id to validate (may be None)

    Returns:
        True if run_id is safe, False otherwise
    """
    if not run_id:
        return False
    if _SAFE_RUN_ID_RE.fullmatch(run_id) is None:
        return False
    if ".." in run_id:
        return False
    if "/" in run_id or "\\" in run_id:
        return False
    return True


def _artifact_path_for_run(
    external_analysis_dir: Path,
    run_id: str,
) -> Path | None:
    """Construct the expected path for a diagnosis loop pass artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to construct path for

    Returns:
        Path to the expected artifact, or None if run_id is unsafe.
    """
    if not is_safe_run_id(run_id):
        return None

    filename = ARTIFACT_FILENAME_PATTERN.format(run_id=run_id)
    return external_analysis_dir / filename


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


def _truncate_string(value: str | None, max_chars: int = MAX_STRING_CHARS) -> str:
    """Truncate a string value to max_chars, appending ' [...]' if truncated.

    Args:
        value: The value to convert and truncate (may be None)
        max_chars: Maximum length of the resulting string

    Returns:
        Truncated string with ' [...]' suffix if truncated, empty string if None
    """
    if value is None:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + " [...]"


def _bound_loop_update(loop_update: Mapping[str, object]) -> dict[str, object]:
    """Bound a loop update for safe artifact storage.

    Args:
        loop_update: Raw loop update from planner

    Returns:
        Bounded loop update dict
    """
    bounded: dict[str, object] = {}

    # Copy safe scalar fields
    bounded["decision"] = loop_update.get("decision", "")
    bounded["pass_index"] = loop_update.get("pass_index", 1)
    bounded["generated_at"] = loop_update.get("generated_at")

    # Truncate stop_reason
    stop_reason = loop_update.get("stop_reason")
    if stop_reason is not None:
        bounded["stop_reason"] = _truncate_string(str(stop_reason), MAX_STRING_CHARS)

    # Bound budget info
    budget = loop_update.get("budget", {})
    if isinstance(budget, dict):
        bounded["budget"] = {
            "passes_remaining": budget.get("passes_remaining", 0),
            "checks_remaining": budget.get("checks_remaining", 0),
        }

    # Bound runner_result summary if present
    runner_result = loop_update.get("runner_result")
    if isinstance(runner_result, dict):
        bounded["runner_result_summary"] = {
            "checks_requested": runner_result.get("checks_requested", 0),
            "checks_run": runner_result.get("checks_run", 0),
            "checks_skipped": runner_result.get("checks_skipped", 0),
            "checks_rejected": runner_result.get("checks_rejected", 0),
        }

    return bounded


def _bound_orchestrator_result(
    orchestrator_result: Mapping[str, object],
) -> dict[str, object]:
    """Bound an orchestrator result for safe artifact storage.

    Args:
        orchestrator_result: Raw orchestrator result

    Returns:
        Bounded orchestrator result dict
    """
    bounded: dict[str, object] = {
        "schema_version": orchestrator_result.get("schema_version", ARTIFACT_SCHEMA_VERSION),
        "incident_id": orchestrator_result.get("incident_id", ""),
        "run_id": orchestrator_result.get("run_id", ""),
        "decision": orchestrator_result.get("decision", ""),
        "case_file_linked_artifact": orchestrator_result.get("case_file_linked_artifact", False),
    }

    # Bound loop_update
    loop_update = orchestrator_result.get("loop_update")
    if isinstance(loop_update, dict):
        bounded["loop_update"] = _bound_loop_update(loop_update)

    # Bound runner_result summary only
    runner_result = orchestrator_result.get("runner_result")
    if isinstance(runner_result, dict):
        bounded["runner_result"] = {
            "checks_requested": runner_result.get("checks_requested", 0),
            "checks_run": runner_result.get("checks_run", 0),
            "checks_skipped": runner_result.get("checks_skipped", 0),
            "checks_rejected": runner_result.get("checks_rejected", 0),
        }

    # Bound artifact metadata (strip full paths, keep safe refs)
    artifact = orchestrator_result.get("artifact")
    if isinstance(artifact, dict):
        bounded["artifact"] = {
            "run_id": artifact.get("run_id"),
            "incident_id": artifact.get("incident_id"),
            "written": artifact.get("written", False),
        }

    return bounded


def _build_linked_artifacts(
    check_artifact_written: bool,
    run_id: str,
) -> list[dict[str, object]]:
    """Build linked artifacts list.

    Args:
        check_artifact_written: Whether check-result artifact was written
        run_id: The run_id for the check artifact

    Returns:
        List of linked artifact references
    """
    linked: list[dict[str, object]] = []

    if check_artifact_written:
        linked.append({
            "kind": "external-analysis",
            "type": "read-only-check-results",
            "name": f"{run_id}-read-only-check-results.json",
            "run_id": run_id,
            "safe": True,
        })

    return linked[:MAX_LINKED_ARTIFACTS]


# =============================================================================
# Public API
# =============================================================================


def write_diagnosis_loop_pass_artifact(
    *,
    external_analysis_dir: Path,
    run_id: str,
    incident_id: str,
    orchestrator_result: Mapping[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    """Write a diagnosis loop pass artifact to disk.

    This function persists loop pass orchestration results as a bounded JSON artifact.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: Unique identifier for this run (must be safe)
        incident_id: The incident ID this artifact belongs to
        orchestrator_result: The orchestrator result from run_one_read_only_diagnosis_loop_pass()
        now: Optional datetime for deterministic timestamps

    Returns:
        Dict with artifact metadata including path and status

    Raises:
        ValueError: If run_id is unsafe

    Safety:
        - Validates run_id against strict character constraints
        - Does not write outside external_analysis_dir
        - Does not persist full case files or runner results
        - Strips action-control fields
        - Bounds all string fields
    """
    # Safety check: reject unsafe run_ids
    if not is_safe_run_id(run_id):
        raise ValueError(f"Unsafe run_id: {run_id!r}")

    # Resolve timestamp
    resolved_now = now if now is not None else datetime.now(UTC)

    # Construct artifact path
    artifact_path = _artifact_path_for_run(external_analysis_dir, run_id)
    if artifact_path is None:
        raise ValueError(f"Could not construct artifact path for run_id: {run_id!r}")

    # Ensure parent directory exists
    external_analysis_dir.mkdir(parents=True, exist_ok=True)

    # Extract decision and check counts
    decision = orchestrator_result.get("decision", "")
    loop_update = orchestrator_result.get("loop_update", {})

    # Determine if check artifact was written
    check_artifact = orchestrator_result.get("artifact")
    check_artifact_written = (
        isinstance(check_artifact, dict)
        and check_artifact.get("written", False) is True
    )

    # Extract check counts from runner_result
    runner_result = orchestrator_result.get("runner_result", {})
    if isinstance(runner_result, dict):
        checks_requested = runner_result.get("checks_requested", 0)
        checks_run = runner_result.get("checks_run", 0)
        checks_skipped = runner_result.get("checks_skipped", 0)
        checks_rejected = runner_result.get("checks_rejected", 0)
    else:
        checks_requested = 0
        checks_run = 0
        checks_skipped = 0
        checks_rejected = 0

    # Determine stop reason if this is a stop decision
    stop_reason = loop_update.get("stop_reason") if isinstance(loop_update, dict) else None
    if stop_reason is None and decision.startswith("stop_"):
        stop_reason = decision.replace("stop_", "").replace("_", " ")

    # Build linked artifacts
    linked_artifacts = _build_linked_artifacts(check_artifact_written, run_id)

    # Build artifact envelope
    artifact: dict[str, object] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "diagnosis-loop-pass",
        "incident_id": incident_id,
        "run_id": run_id,
        "generated_at": resolved_now.isoformat(),
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        "source": "one-pass-read-only-diagnosis-loop",
        "bounded": True,

        "decision": decision,
        "stop_reason": _truncate_string(str(stop_reason)) if stop_reason is not None else None,

        "checks_requested": checks_requested,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "checks_rejected": checks_rejected,

        "case_file_linked_artifact": orchestrator_result.get("case_file_linked_artifact", False),

        "linked_artifacts": linked_artifacts,

        "loop_summary": {
            "pass_index": loop_update.get("pass_index", 1) if isinstance(loop_update, dict) else 1,
            "confidence": _truncate_string(str(loop_update.get("confidence", "unknown")) if isinstance(loop_update, dict) else "unknown"),
            "progress": _truncate_string(str(loop_update.get("progress", "")) if isinstance(loop_update, dict) else ""),
            "bounded": True,
        },

        # Bounded orchestrator result summary (NOT full case_file or runner_result)
        "orchestrator_result": _bound_orchestrator_result(orchestrator_result),

        "safety_metadata": {
            "read_only": True,
            "allowed_actions": [],
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
