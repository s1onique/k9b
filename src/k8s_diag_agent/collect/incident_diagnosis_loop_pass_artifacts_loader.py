"""Pure helper module for loading diagnosis loop pass artifacts.

This module provides read-only logic for loading persisted loop pass artifacts
from bounded JSON artifacts.

Design constraints:
- Bounded file IO only in explicit load functions
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic ordering
- Failure-tolerant loading (missing/malformed artifacts produce empty results)
- Explicit safety metadata

SAFE extraction rules:
- Only artifacts linked by matching run_id from incident signals or explicit list
- Only artifacts where schema version is present
- Only artifacts where incident_id matches current incident (if present)
- Unsafe run_ids are skipped without path construction

Path safety:
- run_id values are validated against strict character constraints
- Unsafe run_ids are skipped without path construction
- Only exact expected filenames are read (no glob/recursive patterns)
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_lifecycle import Incident

__all__ = [
    "load_diagnosis_loop_pass_artifacts_for_incident",
    "is_safe_run_id",
    "DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS",
]


# =============================================================================
# Constants and Patterns
# =============================================================================

# Artifact filename pattern
ARTIFACT_FILENAME_PATTERN = "{run_id}-diagnosis-loop-pass.json"

# Maximum bounds for safety
DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS = 10
MAX_STRING_CHARS = 500


def _truncate_string(value: str | None, max_chars: int = MAX_STRING_CHARS) -> str:
    """Truncate a string value to max_chars, appending ' [...]' if truncated.

    Args:
        value: The value to truncate (may be None)
        max_chars: Maximum length of the resulting string

    Returns:
        Truncated string with ' [...]' suffix if truncated, empty string if None
    """
    if value is None:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + " [...]"


# Strict regex for allowed run_id characters: A-Z a-z 0-9 _ . -
# Excludes: / \ .. and other special characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Forbidden action-control fields
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


# =============================================================================
# Safety Helpers
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
# Safe Field Extraction Helpers
# =============================================================================


def _strip_action_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove action-control fields from a dict.

    Args:
        data: Input dict that may contain action fields

    Returns:
        Filtered dict without action-control fields
    """
    return {k: v for k, v in data.items() if k not in _FORBIDDEN_ACTION_FIELDS}


# =============================================================================
# Artifact Loading
# =============================================================================


def _load_artifact_payload(path: Path) -> dict[str, Any] | None:
    """Load and validate an artifact payload.

    Args:
        path: Path to the artifact file

    Returns:
        Validated artifact dict if file exists and is valid JSON dict,
        None otherwise (file missing, malformed JSON, or non-dict root)
    """
    try:
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        # Must be a dict/mapping
        if not isinstance(raw, dict):
            return None

        return raw
    except (json.JSONDecodeError, OSError):
        return None


def _extract_bounded_loop_pass_entry(
    run_id: str,
    payload: Mapping[str, object],
    current_incident_id: str,
) -> dict[str, object] | None:
    """Extract a bounded loop pass entry from an artifact payload.

    Args:
        run_id: Run ID from the filename
        payload: Loaded artifact payload
        current_incident_id: Incident ID to validate linkage

    Returns:
        Bounded loop pass entry dict, or None if linkage is invalid
    """
    # Validate schema version exists (required for trusted linkage)
    schema_version = payload.get("schema_version")
    if schema_version is None:
        return None

    # Check incident_id linkage if present in artifact
    artifact_incident_id = payload.get("incident_id")
    if artifact_incident_id is not None and artifact_incident_id != current_incident_id:
        # Wrong incident - do not include
        return None

    # Extract bounded metadata
    generated_at = payload.get("generated_at") or ""

    # Extract decision and stop reason
    decision = payload.get("decision", "")
    raw_stop_reason = payload.get("stop_reason")
    stop_reason = _truncate_string(str(raw_stop_reason)) if raw_stop_reason is not None else None

    # Extract check counts
    checks_requested = payload.get("checks_requested", 0)
    checks_run = payload.get("checks_run", 0)
    checks_skipped = payload.get("checks_skipped", 0)
    checks_rejected = payload.get("checks_rejected", 0)

    # Extract linked artifacts (bounded)
    linked_artifacts: list[dict[str, Any]] = []
    raw_linked = payload.get("linked_artifacts", [])
    if isinstance(raw_linked, list):
        for item in raw_linked[:10]:  # Limit to 10
            if isinstance(item, dict):
                safe_item = {
                    "kind": item.get("kind", "unknown"),
                    "type": item.get("type", "unknown"),
                    "name": item.get("name", ""),
                    "run_id": item.get("run_id"),
                    "safe": item.get("safe", False),
                }
                linked_artifacts.append(safe_item)

    # Extract loop summary (truncate string fields for safety)
    loop_summary: dict[str, Any] = {}
    raw_summary = payload.get("loop_summary", {})
    if isinstance(raw_summary, dict):
        loop_summary = {
            "pass_index": raw_summary.get("pass_index", 1),
            "confidence": _truncate_string(str(raw_summary.get("confidence", "unknown"))),
            "progress": _truncate_string(str(raw_summary.get("progress", ""))),
            "bounded": True,
        }

    # Extract orchestrator result summary (bounded)
    orchestrator_result: dict[str, Any] = {}
    raw_result = payload.get("orchestrator_result", {})
    if isinstance(raw_result, dict):
        orchestrator_result = {
            "decision": raw_result.get("decision", ""),
            "case_file_linked_artifact": raw_result.get("case_file_linked_artifact", False),
        }

    # Extract safety metadata if present
    safety_metadata: dict[str, Any] = {}
    raw_safety = payload.get("safety_metadata", {})
    if isinstance(raw_safety, dict):
        safety_metadata = {
            "read_only": raw_safety.get("read_only", True),
            "allowed_actions": [],
            "no_kubernetes_client": raw_safety.get("no_kubernetes_client", True),
            "no_shell": raw_safety.get("no_shell", True),
            "no_subprocess": raw_safety.get("no_subprocess", True),
            "no_kubectl": raw_safety.get("no_kubectl", True),
            "no_mutation": raw_safety.get("no_mutation", True),
            "fake_runner": raw_safety.get("fake_runner", True),
            "bounded": True,
        }

    # Build the entry
    entry: dict[str, object] = {
        "artifact_type": "diagnosis-loop-pass",
        "run_id": run_id,
        "generated_at": str(generated_at) if generated_at else None,
        "decision": decision,
        "stop_reason": stop_reason,
        "checks_requested": checks_requested,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "checks_rejected": checks_rejected,
        "case_file_linked_artifact": payload.get("case_file_linked_artifact", False),
        "linked_artifacts": linked_artifacts,
        "loop_summary": loop_summary,
        "orchestrator_result_summary": orchestrator_result,
        "bounded": True,
        "fake_diagnosis_loop": True,
    }

    # Add optional fields if present
    if artifact_incident_id:
        entry["incident_id"] = artifact_incident_id

    # Add source label
    entry["source"] = payload.get("source", "unknown")

    # Add safety metadata
    if safety_metadata:
        entry["safety_metadata"] = _strip_action_fields(safety_metadata)

    return entry


def load_diagnosis_loop_pass_artifacts_for_incident(
    incident: Incident,
    external_analysis_dir: Path,
    *,
    max_artifacts: int = DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS,
    explicit_run_ids: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Load diagnosis loop pass artifacts for an incident.

    Extracts run_ids from incident signals (and/or explicit run_ids),
    locates corresponding loop pass artifacts, loads and validates them,
    and returns in deterministic order.

    Args:
        incident: The incident to load loop pass artifacts for
        external_analysis_dir: Path to the external-analysis directory
        max_artifacts: Maximum number of artifacts to load (default 10)
        explicit_run_ids: Optional explicit list of run_ids to load artifacts for.
            These are validated with is_safe_run_id() and checked for incident_id
            match. Use this to include artifacts written in the current
            orchestrator pass that may not yet be linked from incident signals.

    Returns:
        List of bounded loop pass entries

    Failure-tolerant behavior:
    - Missing directory: returns empty list
    - Missing artifact: skipped
    - Malformed artifact: skipped
    - Wrong incident linkage: skipped
    - Run_ids beyond max_artifacts: truncated (deterministic)
    - Unsafe run_ids: skipped
    - Duplicate run_ids: deduplicated deterministically

    Note:
        Does not mutate incident or artifacts.
        Does not raise for normal missing/malformed artifact cases.
    """
    # Collect run_ids
    seen: set[str] = set()
    run_ids: list[str] = []

    # Add signal-derived run_ids first (from loop pass signals)
    for signal in incident.signals:
        run_id = signal.run_id
        if run_id is not None and run_id not in seen:
            # Check if this looks like a loop pass run_id (will be validated later)
            seen.add(run_id)
            run_ids.append(run_id)

    # Add explicit run_ids (for orchestrator linkage)
    if explicit_run_ids is not None:
        for run_id in explicit_run_ids:
            if run_id not in seen and is_safe_run_id(run_id):
                seen.add(run_id)
                run_ids.append(run_id)

    # Bound the number of run_ids to check
    if len(run_ids) > max_artifacts * 2:  # Allow checking more than returning
        run_ids = run_ids[: max_artifacts * 2]

    # Early exit if no run_ids or directory doesn't exist
    if not run_ids:
        return []

    if not external_analysis_dir.is_dir():
        return []

    # Load artifacts
    entries: list[dict[str, object]] = []
    current_incident_id = incident.incident_id

    for run_id in run_ids:
        if len(entries) >= max_artifacts:
            break

        # Safety check: skip unsafe run_ids
        if not is_safe_run_id(run_id):
            continue

        # Construct path
        artifact_path = _artifact_path_for_run(external_analysis_dir, run_id)
        if artifact_path is None:
            continue

        # Load payload
        payload = _load_artifact_payload(artifact_path)
        if payload is None:
            continue

        # Extract bounded entry
        entry = _extract_bounded_loop_pass_entry(
            run_id=run_id,
            payload=payload,
            current_incident_id=current_incident_id,
        )

        if entry is not None:
            entries.append(entry)

    # Deterministic ordering: sort by run_id
    entries.sort(key=lambda e: str(e.get("run_id", "")))

    return entries[:max_artifacts]
